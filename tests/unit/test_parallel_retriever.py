import pytest
from pathlib import Path
from typing import Any

from minder.config import MinderConfig, GraphConfig
from minder.graph.nodes.retriever import RetrieverNode
from minder.graph.nodes.parallel_retriever import ParallelRetrieverNode
from minder.graph.state import GraphState


@pytest.fixture
def mock_retriever() -> RetrieverNode:
    # A dummy retriever with some mock logic isn't strictly necessary if we mock the stores
    # but we need to instantiate it.
    class MockEmbeddingProvider:
        def embed(self, text: str) -> Any:
            return [0.1, 0.2]

    class MockVectorStore:
        async def search_documents(self, vector, **kwargs):
            return [{"path": "file_vector.py", "score": 0.9, "content": "mock vector"}]

    r = RetrieverNode(
        top_k=5,
        embedding_provider=MockEmbeddingProvider(),
        vector_store=MockVectorStore(),
        score_threshold=0.0
    )
    return r


@pytest.fixture
def config() -> MinderConfig:
    config = MinderConfig()
    config.graph = GraphConfig(enable_parallel_retrieval=True)
    return config


class _MockGraphTools:
    async def minder_search_graph(self, query: str, **kwargs: Any) -> dict[str, Any]:
        del query, kwargs
        return {
            "results": [
                {
                    "name": "auth_service",
                    "node_type": "service",
                    "repo_name": "demo",
                    "branch": "main",
                    "metadata": {"path": "graph/auth_service"},
                    "score": 0.8,
                }
            ]
        }


@pytest.mark.asyncio
async def test_parallel_retriever_plan_and_merge(mock_retriever: RetrieverNode, config: MinderConfig, tmp_path: Path):
    node = ParallelRetrieverNode(mock_retriever, config, graph_tools=_MockGraphTools())
    state = GraphState(query="mock", repo_path=str(tmp_path))

    # Test plan
    sends = node.plan_retrieval(state)
    assert len(sends) == 3
    assert sends[0].node == "retrieve_strategy"
    assert sends[1].node == "retrieve_strategy"

    strategies = {s.arg["metadata"]["retrieval_strategy"] for s in sends}
    assert strategies == {"vector", "bm25", "knowledge_graph"}

    # Test retrieve vector
    state.metadata["retrieval_strategy"] = "vector"
    vector_res = await node.retrieve_strategy(state)
    assert len(vector_res["retrieved_docs"]) == 1
    assert vector_res["retrieved_docs"][0]["retrieval_strategy"] == "vector"

    # Write a dummy bm25 file
    (tmp_path / "mock.txt").write_text("This is a mock text file.")

    # Test retrieve bm25
    state.metadata["retrieval_strategy"] = "bm25"
    bm25_res = await node.retrieve_strategy(state)
    assert len(bm25_res["retrieved_docs"]) == 1
    assert bm25_res["retrieved_docs"][0]["retrieval_strategy"] == "bm25"

    # Test retrieve knowledge graph
    state.metadata["retrieval_strategy"] = "knowledge_graph"
    graph_res = await node.retrieve_strategy(state)
    assert len(graph_res["retrieved_docs"]) == 1
    assert graph_res["retrieved_docs"][0]["retrieval_strategy"] == "knowledge_graph"

    # Test merge
    state.retrieved_docs = (
        vector_res["retrieved_docs"]
        + bm25_res["retrieved_docs"]
        + graph_res["retrieved_docs"]
    )

    merge_res = await node.merge_retrieved(state)
    assert "reranked_docs" in merge_res
    reranked = merge_res["reranked_docs"]

    # Verify deduplication and correct outputs
    assert len(reranked) == 3
    paths = {doc["path"] for doc in reranked}
    assert "file_vector.py" in paths
    assert str(tmp_path / "mock.txt") in paths
    assert "graph/auth_service" in paths
