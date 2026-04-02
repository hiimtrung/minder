from pathlib import Path

import pytest

from minder.embedding.qwen import QwenEmbeddingProvider
from minder.graph.nodes.retriever import RetrieverNode
from minder.graph.state import GraphState
from minder.store.document import DocumentStore
from minder.store.error import ErrorStore
from minder.store.relational import RelationalStore
from minder.store.vector import VectorStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


async def test_vector_store_searches_documents(store: RelationalStore) -> None:
    document_store = DocumentStore(store)
    error_store = ErrorStore(store)
    embedder = QwenEmbeddingProvider("~/.minder/models/qwen.gguf")
    vector_store = VectorStore(document_store, error_store)

    await document_store.create_document(
        title="feature.py",
        content="def work():\n    return 'ok'\n",
        doc_type="code",
        source_path="/tmp/feature.py",
        project="demo",
        embedding=embedder.embed("work feature implementation"),
    )

    hits = await vector_store.search_documents(
        embedder.embed("work feature implementation"),
        project="demo",
        limit=3,
        score_threshold=0.0,
    )
    assert hits
    assert hits[0]["path"] == "/tmp/feature.py"


async def test_retriever_prefers_vector_hits(store: RelationalStore, tmp_path: Path) -> None:
    document_store = DocumentStore(store)
    error_store = ErrorStore(store)
    embedder = QwenEmbeddingProvider("~/.minder/models/qwen.gguf")
    vector_store = VectorStore(document_store, error_store)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "fallback.py").write_text("def fallback():\n    return False\n", encoding="utf-8")

    await document_store.create_document(
        title="semantic.py",
        content="def semantic():\n    return True\n",
        doc_type="code",
        source_path="/semantic.py",
        project=repo_path.name,
        embedding=embedder.embed("semantic retrieval target"),
    )

    retriever = RetrieverNode(
        top_k=5,
        embedding_provider=embedder,
        vector_store=vector_store,
        score_threshold=0.0,
    )
    state = GraphState(
        query="semantic retrieval target",
        repo_path=str(repo_path),
        metadata={"project_name": repo_path.name},
    )
    state = await retriever.run(state)

    assert state.metadata["retrieval_mode"] == "vector"
    assert state.retrieved_docs[0]["path"] == "/semantic.py"
