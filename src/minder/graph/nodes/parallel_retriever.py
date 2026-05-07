from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from langgraph.types import Send

from minder.config import MinderConfig
from minder.graph.nodes.retriever import RetrieverNode
from minder.graph.state import GraphState
from minder.retrieval import HybridRetriever

if TYPE_CHECKING:
    from minder.tools.graph import GraphTools


_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")


class ParallelRetrieverNode:
    def __init__(
        self,
        retriever: RetrieverNode,
        config: MinderConfig,
        *,
        graph_tools: GraphTools | None = None,
    ) -> None:
        self._retriever = retriever
        self._config = config
        self._graph_tools = graph_tools

    def plan_retrieval(self, state: GraphState) -> list[Send]:
        strategies = ["vector", "bm25", "knowledge_graph"]
        sends: list[Send] = []
        for strategy in strategies:
            payload = state.model_dump(mode="python")
            metadata = dict(payload.get("metadata", {}) or {})
            metadata["retrieval_strategy"] = strategy
            payload["metadata"] = metadata
            sends.append(Send("retrieve_strategy", payload))
        return sends

    async def retrieve_strategy(self, state: GraphState) -> dict[str, Any]:
        strategy = str(state.metadata.get("retrieval_strategy", "vector") or "vector")
        if strategy == "lexical":
            strategy = "bm25"

        docs: list[dict[str, Any]] = []
        if strategy == "vector":
            docs = await self._vector_search(state)
        elif strategy == "bm25":
            docs = self._bm25_search(state)
        elif strategy == "knowledge_graph":
            docs = await self._knowledge_graph_search(state)

        return {"retrieved_docs": docs}

    async def merge_retrieved(self, state: GraphState) -> dict[str, Any]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for doc in state.retrieved_docs:
            key = str(doc.get("path") or doc.get("name") or doc.get("title") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(doc)

        vector_results = [
            doc
            for doc in unique
            if str(doc.get("retrieval_strategy", "")) == "vector"
        ]
        ranked = HybridRetriever(alpha=self._config.retrieval.hybrid_alpha).merge(
            state.query,
            vector_results=vector_results,
            corpus=unique,
            limit=int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k)),
        )
        top_k = int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k))
        final_docs = ranked[:top_k]
        return {"retrieved_docs": final_docs, "reranked_docs": final_docs}

    async def _vector_search(self, state: GraphState) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        embedding_provider = getattr(self._retriever, "_embedding_provider", None)
        vector_store = getattr(self._retriever, "_vector_store", None)
        top_k = int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k))
        score_threshold = float(
            getattr(
                self._retriever,
                "_score_threshold",
                self._config.retrieval.similarity_threshold,
            )
        )
        if embedding_provider is not None and vector_store is not None:
            embedded = embedding_provider.embed(state.query)
            project = state.metadata.get("project_name")
            semantic_hits = await vector_store.search_documents(
                embedded,
                project=str(project) if isinstance(project, str) else None,
                limit=top_k,
                score_threshold=score_threshold,
            )
            for doc in semantic_hits or []:
                doc["retrieval_strategy"] = "vector"
                docs.append(doc)
        return docs

    def _bm25_search(self, state: GraphState) -> list[dict[str, Any]]:
        query_terms = self._tokenize(state.query)
        if not query_terms:
            return []

        corpus = self._collect_repo_documents(state.repo_path)
        if not corpus:
            return []

        document_frequencies = {
            term: sum(1 for doc in corpus if term in cast(list[str], doc["_tokens"]))
            for term in query_terms
        }
        average_doc_length = sum(len(cast(list[str], doc["_tokens"])) for doc in corpus) / len(corpus)
        k1 = 1.5
        b = 0.75
        total_docs = len(corpus)

        ranked: list[dict[str, Any]] = []
        for doc in corpus:
            tokens = cast(list[str], doc["_tokens"])
            token_count = max(1, len(tokens))
            score = 0.0
            for term in query_terms:
                term_frequency = tokens.count(term)
                if term_frequency == 0:
                    continue
                doc_freq = document_frequencies.get(term, 0)
                idf = math.log(1 + ((total_docs - doc_freq + 0.5) / (doc_freq + 0.5)))
                numerator = term_frequency * (k1 + 1)
                denominator = term_frequency + k1 * (
                    1 - b + b * (token_count / max(average_doc_length, 1.0))
                )
                score += idf * (numerator / denominator)
            if score <= 0.0:
                continue
            ranked.append(
                {
                    "title": doc["title"],
                    "path": doc["path"],
                    "content": doc["content"],
                    "score": score,
                    "doc_type": doc["doc_type"],
                    "retrieval_strategy": "bm25",
                }
            )

        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        top_k = int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k))
        return ranked[:top_k]

    async def _knowledge_graph_search(self, state: GraphState) -> list[dict[str, Any]]:
        if self._graph_tools is not None:
            result = await self._graph_tools.minder_search_graph(
                state.query,
                repo_path=state.repo_path,
                repo_id=str(state.repo_id) if state.repo_id else None,
                repo_name=cast(str | None, state.metadata.get("project_name")),
                limit=int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k)),
            )
            return [self._graph_result_to_doc(item) for item in result.get("results", [])]

        cross_repo_graph = state.workflow_context.get("cross_repo_graph")
        if isinstance(cross_repo_graph, dict):
            return [
                self._graph_result_to_doc(item)
                for item in list(cross_repo_graph.get("results", []) or [])[
                    : int(getattr(self._retriever, "_top_k", self._config.retrieval.top_k))
                ]
                if isinstance(item, dict)
            ]
        return []

    def _collect_repo_documents(self, repo_path: str | None) -> list[dict[str, Any]]:
        root = Path(repo_path or ".")
        if not root.exists():
            return []

        candidates: list[dict[str, Any]] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") and part != ".minder" for part in path.parts):
                continue
            if path.suffix not in {".py", ".md", ".txt", ".json"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            tokens = self._tokenize(content)
            if not tokens:
                continue
            candidates.append(
                {
                    "title": path.name,
                    "path": str(path),
                    "content": content,
                    "doc_type": "code" if path.suffix == ".py" else "markdown",
                    "_tokens": tokens,
                }
            )
        return candidates

    @staticmethod
    def _graph_result_to_doc(item: dict[str, Any]) -> dict[str, Any]:
        node_type = str(item.get("node_type", "graph_node") or "graph_node")
        name = str(item.get("name", "") or "")
        metadata = dict(item.get("metadata", {}) or {})
        path = str(
            item.get("path")
            or metadata.get("path")
            or f"graph://{node_type}/{name or 'unknown'}"
        )
        content = "\n".join(
            [
                f"node_type: {node_type}",
                f"name: {name}",
                f"repo: {item.get('repo_name', '')}",
                f"branch: {item.get('branch', '')}",
                f"metadata: {metadata}",
            ]
        )
        return {
            "title": name or path,
            "path": path,
            "content": content,
            "score": float(item.get("score", 0.0)),
            "doc_type": node_type,
            "retrieval_strategy": "knowledge_graph",
        }

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(text) if len(token) > 2]
