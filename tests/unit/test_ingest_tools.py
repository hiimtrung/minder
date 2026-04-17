from pathlib import Path
from typing import Any

import pytest

from minder.embedding.local import LocalEmbeddingProvider
from minder.store.document import DocumentStore
from minder.store.relational import RelationalStore
from minder.tools.ingest import IngestTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.mark.asyncio
async def test_ingest_directory_upserts_supported_files(store: RelationalStore, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (repo / "b.md").write_text("# Title\n", encoding="utf-8")
    (repo / "ignored.bin").write_bytes(b"\x00\x01")

    tools = IngestTools(DocumentStore(store), LocalEmbeddingProvider("~/.minder/models/local.gguf"))
    result = await tools.minder_ingest_directory(str(repo), project=repo.name)

    assert result["ingested_count"] == 2
    docs = await DocumentStore(store).list_documents(project=repo.name)
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_ingest_directory_removes_stale_documents(store: RelationalStore, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "a.py"
    file_path.write_text("def a():\n    return 1\n", encoding="utf-8")

    document_store = DocumentStore(store)
    tools = IngestTools(document_store, LocalEmbeddingProvider("~/.minder/models/local.gguf"))
    await tools.minder_ingest_directory(str(repo), project=repo.name)

    file_path.unlink()
    await tools.minder_ingest_directory(str(repo), project=repo.name)
    docs = await document_store.list_documents(project=repo.name)
    assert docs == []


class _CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return [0.1, 0.2, 0.3, 0.4]


class _VectorSpy:
    def __init__(self) -> None:
        self.calls = 0

    async def upsert_document(self, doc_id: Any, embedding: list[float], payload: dict[str, Any]) -> None:
        self.calls += 1

    async def delete_documents(self, doc_ids: list[Any]) -> None:
        return None


@pytest.mark.asyncio
async def test_ingest_directory_skips_unchanged_files_without_reembedding(
    store: RelationalStore,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    document_store = DocumentStore(store)
    embedder = _CountingEmbedder()
    vector_store = _VectorSpy()
    tools = IngestTools(document_store, embedder, vector_store=vector_store)

    await tools.minder_ingest_directory(str(repo), project=repo.name)
    await tools.minder_ingest_directory(str(repo), project=repo.name)

    assert embedder.calls == 1
    assert vector_store.calls == 1
