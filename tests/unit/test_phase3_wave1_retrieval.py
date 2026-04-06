"""
Unit tests for Phase 3 Wave 1 — Retrieval Infrastructure.

Covers:
  - P3-T04: MMR diversity filtering
  - P3-T02: BM25 hybrid retrieval
  - P3-T03: Multi-hop retrieval
  - P3-T01: RerankerNode (cross-encoder monkeypatch + MMR path + passthrough)
  - P3-T07: AST-aware code chunking (Python + TypeScript + Java)
  - P3-T08: Text chunking (markdown heading split + sliding window)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(path: str, content: str, score: float = 0.5) -> dict:
    return {"path": path, "title": path, "content": content, "score": score}


def _unit_vec(dim: int, hot: int) -> list[float]:
    """Return a unit vector with 1.0 at position `hot`."""
    v = [0.0] * dim
    v[hot % dim] = 1.0
    return v


# ===========================================================================
# P3-T04: MMR
# ===========================================================================


class TestMMR:
    def test_empty_candidates_returns_empty(self) -> None:
        from minder.retrieval.mmr import mmr_rerank
        assert mmr_rerank([1.0, 0.0], [], top_k=3) == []

    def test_returns_at_most_top_k(self) -> None:
        from minder.retrieval.mmr import mmr_rerank
        docs = [{"path": f"d{i}", "score": float(i)} for i in range(10)]
        result = mmr_rerank([1.0, 0.0], docs, top_k=3)
        assert len(result) <= 3

    def test_lambda_1_equals_relevance_order(self) -> None:
        """lambda_mult=1 → pure relevance, same order as cosine ranking."""
        from minder.retrieval.mmr import mmr_rerank
        # 4 docs with embeddings aligned to query
        query_emb = [1.0, 0.0, 0.0, 0.0]
        docs = [
            {"path": "a", "embedding": [0.9, 0.0, 0.0, 0.0], "score": 0.9},
            {"path": "b", "embedding": [0.7, 0.0, 0.0, 0.0], "score": 0.7},
            {"path": "c", "embedding": [0.5, 0.0, 0.0, 0.0], "score": 0.5},
            {"path": "d", "embedding": [0.3, 0.0, 0.0, 0.0], "score": 0.3},
        ]
        result = mmr_rerank(query_emb, docs, top_k=4, lambda_mult=1.0)
        paths = [d["path"] for d in result]
        assert paths == ["a", "b", "c", "d"]

    def test_lambda_0_maximises_diversity(self) -> None:
        """lambda_mult=0 → max diversity: after first pick, next should differ maximally."""
        from minder.retrieval.mmr import mmr_rerank
        # Two clusters: (a,b) very similar, c orthogonal
        query_emb = [1.0, 0.0]
        docs = [
            {"path": "a", "embedding": [1.0, 0.0], "score": 0.9},
            {"path": "b", "embedding": [0.99, 0.14], "score": 0.88},  # near-duplicate of a
            {"path": "c", "embedding": [0.0, 1.0], "score": 0.5},     # orthogonal
        ]
        result = mmr_rerank(query_emb, docs, top_k=2, lambda_mult=0.0)
        paths = [d["path"] for d in result]
        # First pick is a (highest relevance); second should be c (most diverse from a)
        assert paths[0] == "a"
        assert paths[1] == "c"

    def test_docs_without_embeddings_use_score_fallback(self) -> None:
        from minder.retrieval.mmr import mmr_rerank
        docs = [
            {"path": "x", "score": 0.8},
            {"path": "y", "score": 0.6},
            {"path": "z", "score": 0.4},
        ]
        result = mmr_rerank([1.0, 0.0], docs, top_k=2)
        assert len(result) == 2


# ===========================================================================
# P3-T02: BM25 Hybrid
# ===========================================================================


class TestHybridRetriever:
    def test_invalid_alpha_raises(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        with pytest.raises(ValueError):
            HybridRetriever(alpha=1.5)
        with pytest.raises(ValueError):
            HybridRetriever(alpha=-0.1)

    def test_alpha_1_pure_vector_order(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        hr = HybridRetriever(alpha=1.0)
        vec = [
            _make_doc("a.py", "function foo", score=0.9),
            _make_doc("b.py", "class Bar",    score=0.4),
        ]
        result = hr.merge("foo", vec, vec, limit=2)
        assert result[0]["path"] == "a.py"

    def test_alpha_0_pure_bm25_keyword_match(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        hr = HybridRetriever(alpha=0.0)
        # Both have same vector score; b.py contains more "widget" hits
        vec = [
            _make_doc("a.py", "generic content about things", score=0.5),
            _make_doc("b.py", "widget widget widget component widget", score=0.5),
        ]
        result = hr.merge("widget", vec, vec, limit=2)
        assert result[0]["path"] == "b.py"

    def test_half_blend_returns_merged_scores(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        hr = HybridRetriever(alpha=0.5)
        vec = [_make_doc(f"doc{i}.py", f"content number {i}", score=float(i) * 0.1) for i in range(5)]
        result = hr.merge("content", vec, vec, limit=3)
        assert len(result) == 3
        # Each result should have the extra keys
        for doc in result:
            assert "bm25_score" in doc
            assert "vector_score" in doc

    def test_empty_inputs_returns_empty(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        hr = HybridRetriever()
        assert hr.merge("query", [], [], limit=5) == []

    def test_limit_respected(self) -> None:
        from minder.retrieval.hybrid import HybridRetriever
        hr = HybridRetriever()
        docs = [_make_doc(f"d{i}.py", "content", score=0.5) for i in range(20)]
        result = hr.merge("content", docs, docs, limit=7)
        assert len(result) <= 7


# ===========================================================================
# P3-T03: Multi-Hop
# ===========================================================================


class TestMultiHopRetriever:
    @pytest.mark.asyncio
    async def test_single_hop_returns_results(self) -> None:
        from minder.retrieval.multi_hop import MultiHopRetriever
        docs = [_make_doc("x.py", "hello world", score=0.8)]

        async def _retrieve(query: str, *, limit: int) -> list[dict]:
            return docs[:limit]

        mhr = MultiHopRetriever(_retrieve, max_hops=1)
        result = await mhr.retrieve("hello", limit=5)
        assert result[0]["path"] == "x.py"
        assert result[0]["hop"] == 1

    @pytest.mark.asyncio
    async def test_deduplicates_across_hops(self) -> None:
        from minder.retrieval.multi_hop import MultiHopRetriever
        doc_a = _make_doc("a.py", "alpha bravo", score=0.9)
        doc_b = _make_doc("b.py", "bravo charlie", score=0.7)
        calls: list[str] = []

        async def _retrieve(query: str, *, limit: int) -> list[dict]:
            calls.append(query)
            return [doc_a, doc_b][:limit]

        mhr = MultiHopRetriever(_retrieve, max_hops=2)
        result = await mhr.retrieve("alpha", limit=5)
        # doc_a and doc_b should appear exactly once each
        paths = [d["path"] for d in result]
        assert len(paths) == len(set(paths))
        assert len(calls) == 2  # two hops were attempted

    @pytest.mark.asyncio
    async def test_second_hop_query_differs_from_first(self) -> None:
        from minder.retrieval.multi_hop import MultiHopRetriever
        queries_seen: list[str] = []

        async def _retrieve(query: str, *, limit: int) -> list[dict]:
            queries_seen.append(query)
            return [_make_doc("x.py", "document containing keyword expansion terms here", score=0.5)]

        mhr = MultiHopRetriever(_retrieve, max_hops=2)
        await mhr.retrieve("original query", limit=3)
        assert len(queries_seen) == 2
        # Second hop query should contain the original terms + expansion
        assert "original" in queries_seen[0]
        assert len(queries_seen[1]) >= len(queries_seen[0])

    @pytest.mark.asyncio
    async def test_max_hops_respected(self) -> None:
        from minder.retrieval.multi_hop import MultiHopRetriever
        call_count = 0

        async def _retrieve(query: str, *, limit: int) -> list[dict]:
            nonlocal call_count
            call_count += 1
            return [_make_doc(f"doc{call_count}.py", f"unique content {call_count}", score=0.5)]

        mhr = MultiHopRetriever(_retrieve, max_hops=4)
        await mhr.retrieve("query", limit=10)
        assert call_count == 4


# ===========================================================================
# P3-T01: RerankerNode
# ===========================================================================


class TestRerankerNode:
    @pytest.mark.asyncio
    async def test_passthrough_when_no_embedder(self) -> None:
        from minder.graph.nodes.reranker import RerankerNode
        from minder.graph.state import GraphState
        node = RerankerNode(top_k=3)
        docs = [_make_doc(f"d{i}.py", "content", score=float(i)) for i in range(5)]
        state = GraphState(query="test", retrieved_docs=docs)
        state = await node.run(state)
        assert len(state.reranked_docs) <= 3
        assert state.metadata["reranker_runtime"] == "passthrough"

    @pytest.mark.asyncio
    async def test_empty_docs_returns_empty(self) -> None:
        from minder.graph.nodes.reranker import RerankerNode
        from minder.graph.state import GraphState
        node = RerankerNode()
        state = GraphState(query="test", retrieved_docs=[])
        state = await node.run(state)
        assert state.reranked_docs == []

    @pytest.mark.asyncio
    async def test_mmr_path_with_embedding_provider(self) -> None:
        from minder.graph.nodes.reranker import RerankerNode
        from minder.graph.state import GraphState

        class FakeEmbedder:
            def embed(self, text: str) -> list[float]:
                # Each unique text gets a different direction
                h = hash(text) % 8
                v = [0.0] * 8
                v[h] = 1.0
                return v

        node = RerankerNode(top_k=3, embedding_provider=FakeEmbedder())  # type: ignore[arg-type]
        docs = [_make_doc(f"d{i}.py", f"unique content number {i}", score=0.5) for i in range(6)]
        state = GraphState(query="content", retrieved_docs=docs)
        state = await node.run(state)
        assert len(state.reranked_docs) <= 3
        assert state.metadata["reranker_runtime"] == "mmr"

    @pytest.mark.asyncio
    async def test_cross_encoder_path_monkeypatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import minder.graph.nodes.reranker as reranker_module

        class FakeCE:
            def __init__(self, model_name: str) -> None:
                pass

            def predict(self, pairs: list) -> list[float]:
                # Reverse scoring: shorter content = higher score
                return [1.0 / max(len(p[1]), 1) for p in pairs]

        monkeypatch.setattr(reranker_module, "module_available", lambda _: True)
        monkeypatch.setattr(reranker_module, "load_attr", lambda _m, _a: FakeCE)

        from minder.graph.nodes.reranker import RerankerNode
        from minder.graph.state import GraphState

        node = RerankerNode(top_k=3)
        docs = [
            _make_doc("short.py", "x", score=0.1),
            _make_doc("medium.py", "medium content here", score=0.5),
            _make_doc("long.py",  "a very long content string indeed", score=0.9),
        ]
        state = GraphState(query="test", retrieved_docs=docs)
        state = await node.run(state)
        assert state.metadata["reranker_runtime"] == "cross_encoder"
        # Short content should rank highest (score = 1/len)
        assert state.reranked_docs[0]["path"] == "short.py"

    @pytest.mark.asyncio
    async def test_reranker_wired_in_graph_executor(self) -> None:
        """Confirm RerankerNode is called when present in GraphNodes."""
        from minder.graph.executor import GraphNodes, InternalGraphExecutor
        from minder.graph.nodes import (
            EvaluatorNode, GuardNode, LLMNode, PlanningNode,
            ReasoningNode, RerankerNode, RetrieverNode, VerificationNode, WorkflowPlannerNode,
        )
        from minder.graph.state import GraphState
        from minder.llm.qwen import QwenLocalLLM
        from minder.store.relational import RelationalStore

        store = RelationalStore("sqlite+aiosqlite:///:memory:")
        await store.init_db()

        fired = {"reranker": False}

        class SpyReranker(RerankerNode):
            async def run(self, state: GraphState) -> GraphState:
                fired["reranker"] = True
                state.reranked_docs = list(state.retrieved_docs)
                state.metadata["reranker_runtime"] = "spy"
                return state

        nodes = GraphNodes(
            workflow_planner=WorkflowPlannerNode(store),
            planning=PlanningNode(),
            retriever=RetrieverNode(top_k=1),
            reranker=SpyReranker(),
            reasoning=ReasoningNode(),
            llm=LLMNode(primary=QwenLocalLLM("~/.minder/models/qwen.gguf")),
            guard=GuardNode(),
            verification=VerificationNode(sandbox="subprocess"),
            evaluator=EvaluatorNode(),
        )
        state = GraphState(query="hello", repo_path=".")
        state = await InternalGraphExecutor(nodes).run(state)
        assert fired["reranker"] is True

        await store.dispose()

    @pytest.mark.asyncio
    async def test_no_reranker_in_graph_nodes_skips_node(self) -> None:
        """GraphNodes without reranker (default None) still runs cleanly."""
        from minder.graph.executor import GraphNodes, InternalGraphExecutor
        from minder.graph.nodes import (
            EvaluatorNode, GuardNode, LLMNode, PlanningNode,
            ReasoningNode, RetrieverNode, VerificationNode, WorkflowPlannerNode,
        )
        from minder.graph.state import GraphState
        from minder.llm.qwen import QwenLocalLLM
        from minder.store.relational import RelationalStore

        store = RelationalStore("sqlite+aiosqlite:///:memory:")
        await store.init_db()

        nodes = GraphNodes(
            workflow_planner=WorkflowPlannerNode(store),
            planning=PlanningNode(),
            retriever=RetrieverNode(top_k=1),
            reasoning=ReasoningNode(),
            llm=LLMNode(primary=QwenLocalLLM("~/.minder/models/qwen.gguf")),
            guard=GuardNode(),
            verification=VerificationNode(sandbox="subprocess"),
            evaluator=EvaluatorNode(),
        )
        state = GraphState(query="hello", repo_path=".")
        state = await InternalGraphExecutor(nodes).run(state)
        assert state.metadata.get("reranker_runtime") is None  # not set

        await store.dispose()


# ===========================================================================
# P3-T07: CodeSplitter
# ===========================================================================


class TestCodeSplitter:
    def test_python_splits_at_function_boundaries(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = """\
import os

def foo():
    return 1

def bar():
    return 2

class Baz:
    pass
"""
        splitter = CodeSplitter()
        chunks = splitter.split(code, language="python")
        names = [c.symbol_name for c in chunks]
        assert "foo" in names
        assert "bar" in names
        assert "Baz" in names

    def test_python_imports_prepended_to_each_chunk(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = """\
import os
from pathlib import Path

def my_func():
    return Path(".")
"""
        splitter = CodeSplitter()
        chunks = splitter.split(code, language="python")
        assert len(chunks) == 1
        assert "import os" in chunks[0].content
        assert "from pathlib import Path" in chunks[0].content

    def test_python_no_top_symbols_returns_whole_file(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = "x = 1\ny = 2\n"
        splitter = CodeSplitter()
        chunks = splitter.split(code, language="python")
        assert len(chunks) == 1
        assert chunks[0].symbol_name is None

    def test_python_line_numbers_are_correct(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        chunks = CodeSplitter().split(code, language="python")
        foo_chunk = next(c for c in chunks if c.symbol_name == "foo")
        assert foo_chunk.start_line == 1

    def test_typescript_falls_back_to_brace_split(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = """\
function hello() {
  return "world";
}

class Greeter {
  greet() { return "hi"; }
}
"""
        chunks = CodeSplitter().split(code, language="typescript")
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.language == "typescript"

    def test_java_falls_back_to_brace_split(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        code = """\
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
"""
        chunks = CodeSplitter().split(code, language="java")
        assert len(chunks) >= 1
        assert chunks[0].language == "java"

    def test_empty_code_returns_empty(self) -> None:
        from minder.chunking.code_splitter import CodeSplitter
        assert CodeSplitter().split("", language="python") == []
        assert CodeSplitter().split("   \n", language="python") == []


# ===========================================================================
# P3-T08: TextSplitter
# ===========================================================================


class TestTextSplitter:
    def test_empty_text_returns_empty(self) -> None:
        from minder.chunking.splitter import TextSplitter
        assert TextSplitter().split("") == []

    def test_invalid_chunk_size_raises(self) -> None:
        from minder.chunking.splitter import TextSplitter
        with pytest.raises(ValueError):
            TextSplitter(chunk_size=0)
        with pytest.raises(ValueError):
            TextSplitter(chunk_size=100, overlap=100)

    def test_short_text_returns_single_chunk(self) -> None:
        from minder.chunking.splitter import TextSplitter
        text = "Short text."
        chunks = TextSplitter(chunk_size=512).split(text)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_chunk_size_respected(self) -> None:
        from minder.chunking.splitter import TextSplitter
        text = "x" * 2000
        splitter = TextSplitter(chunk_size=200, overlap=20)
        chunks = splitter.split(text)
        for chunk in chunks:
            assert len(chunk.content) <= 200

    def test_overlap_spans_adjacent_chunks(self) -> None:
        from minder.chunking.splitter import TextSplitter
        # text is 300 chars; chunk_size=200, overlap=50 → step=150
        text = "A" * 300
        splitter = TextSplitter(chunk_size=200, overlap=50)
        chunks = splitter.split(text)
        assert len(chunks) >= 2
        # Second chunk's start_char should be < first chunk's end_char (overlap)
        assert chunks[1].start_char < chunks[0].end_char

    def test_markdown_heading_split(self) -> None:
        from minder.chunking.splitter import TextSplitter
        text = "# Section One\n\ncontent one\n\n# Section Two\n\ncontent two\n"
        chunks = TextSplitter(chunk_size=512).split(text)
        assert len(chunks) == 2
        assert "Section One" in chunks[0].content
        assert "Section Two" in chunks[1].content

    def test_char_offsets_are_consistent(self) -> None:
        from minder.chunking.splitter import TextSplitter
        text = "Hello World " * 100
        splitter = TextSplitter(chunk_size=100, overlap=10)
        chunks = splitter.split(text)
        assert chunks[0].start_char == 0
        for c in chunks:
            assert c.end_char > c.start_char
            assert text[c.start_char : c.end_char] == c.content
