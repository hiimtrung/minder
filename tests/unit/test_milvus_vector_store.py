from __future__ import annotations

from dataclasses import dataclass
import uuid

import pytest

from minder.store.milvus.vector_store import MilvusVectorStore


class _FakeIndexParams:
    def __init__(self) -> None:
        self.indexes: list[dict[str, str]] = []

    def add_index(self, **kwargs: str) -> None:
        self.indexes.append(kwargs)


class _FakePyMilvusClient:
    def __init__(self, *, has_collection: bool, dim: int) -> None:
        self._has_collection = has_collection
        self._dim = dim
        self.drop_calls: list[str] = []
        self.create_calls: list[dict[str, object]] = []
        self.upsert_calls: list[dict[str, object]] = []
        self.search_results: list[list[object]] = []

    def has_collection(self, collection_name: str) -> bool:
        return self._has_collection

    def describe_collection(self, collection_name: str) -> dict[str, object]:
        return {
            "collection_name": collection_name,
            "fields": [
                {"name": "id"},
                {"name": "embedding", "params": {"dim": str(self._dim)}},
            ],
        }

    def drop_collection(self, collection_name: str) -> None:
        self.drop_calls.append(collection_name)
        self._has_collection = False

    def prepare_index_params(self) -> _FakeIndexParams:
        return _FakeIndexParams()

    def create_collection(
        self,
        *,
        collection_name: str,
        schema: dict[str, int],
        index_params: _FakeIndexParams,
    ) -> None:
        self.create_calls.append(
            {
                "collection_name": collection_name,
                "schema": schema,
                "indexes": list(index_params.indexes),
            }
        )
        self._has_collection = True
        self._dim = schema["dim"]

    def upsert(self, *, collection_name: str, data: list[dict[str, object]]) -> None:
        self.upsert_calls.append({"collection_name": collection_name, "data": data})

    def search(
        self,
        *,
        collection_name: str,
        data: list[list[float]],
        filter: str,
        limit: int,
        output_fields: list[str],
    ) -> list[list[object]]:
        return self.search_results


class _FakeMilvusClient:
    def __init__(self, client: _FakePyMilvusClient) -> None:
        self.client = client


@dataclass
class _FakeDocument:
    id: uuid.UUID
    title: str
    source_path: str
    content: str
    doc_type: str


class _FakeDocumentStore:
    def __init__(self, documents: list[_FakeDocument] | None = None) -> None:
        self.documents = documents or []
        self.requested_ids: list[uuid.UUID] = []

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[_FakeDocument]:
        self.requested_ids = list(doc_ids)
        wanted = set(doc_ids)
        return [document for document in self.documents if document.id in wanted]


class _FakeEntity:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def get(self, key: str, default: object = None) -> object:
        if key == "payload":
            return self._payload
        return default


class _FakeHit:
    def __init__(self, doc_id: uuid.UUID, distance: float, payload: dict[str, object]) -> None:
        self.id = str(doc_id)
        self.distance = distance
        self.entity = _FakeEntity(payload)


@pytest.mark.asyncio
async def test_upsert_recreates_collection_when_dimension_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakePyMilvusClient(has_collection=True, dim=1024)
    document_store = _FakeDocumentStore()

    monkeypatch.setattr(
        "minder.store.milvus.vector_store.get_document_schema",
        lambda dim: {"dim": dim},
    )

    store = MilvusVectorStore(
        _FakeMilvusClient(fake_client),
        document_store,
        prefix="demo_",
        dimensions=768,
    )

    await store.upsert_document(
        uuid.uuid4(),
        [0.1] * 768,
        {"project": "repo", "doc_type": "code", "title": "a.py"},
    )

    assert fake_client.drop_calls == ["demo_documents"]
    assert len(fake_client.create_calls) == 1
    assert fake_client.create_calls[0]["schema"] == {"dim": 768}
    assert len(fake_client.upsert_calls) == 1
    assert fake_client.upsert_calls[0]["data"][0]["payload"] == {
        "title": "a.py",
        "source_path": "",
        "doc_type": "code",
        "project": "repo",
    }


@pytest.mark.asyncio
async def test_setup_keeps_collection_when_dimension_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakePyMilvusClient(has_collection=True, dim=768)
    document_store = _FakeDocumentStore()

    monkeypatch.setattr(
        "minder.store.milvus.vector_store.get_document_schema",
        lambda dim: {"dim": dim},
    )

    store = MilvusVectorStore(
        _FakeMilvusClient(fake_client),
        document_store,
        prefix="demo_",
        dimensions=768,
    )

    await store.setup()

    assert fake_client.drop_calls == []
    assert fake_client.create_calls == []


def test_validate_embedding_length_raises_for_mismatched_query_dimension() -> None:
    fake_client = _FakePyMilvusClient(has_collection=False, dim=768)
    store = MilvusVectorStore(_FakeMilvusClient(fake_client), _FakeDocumentStore(), dimensions=768)

    with pytest.raises(ValueError, match="Embedding length 1024 does not match configured Milvus dimension 768"):
        store._validate_embedding_length([0.1] * 1024)


@pytest.mark.asyncio
async def test_search_hydrates_content_from_document_store(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakePyMilvusClient(has_collection=True, dim=768)
    doc_id = uuid.uuid4()
    fake_client.search_results = [
        [
            _FakeHit(
                doc_id,
                0.91,
                {
                    "title": "fallback-title",
                    "source_path": "/tmp/fallback.py",
                    "doc_type": "code",
                    "project": "repo",
                },
            )
        ]
    ]
    document_store = _FakeDocumentStore(
        [
            _FakeDocument(
                id=doc_id,
                title="real-title",
                source_path="/repo/app.py",
                content="print('hello')",
                doc_type="code",
            )
        ]
    )

    monkeypatch.setattr(
        "minder.store.milvus.vector_store.get_document_schema",
        lambda dim: {"dim": dim},
    )

    store = MilvusVectorStore(
        _FakeMilvusClient(fake_client),
        document_store,
        prefix="demo_",
        dimensions=768,
    )

    results = await store.search_documents([0.1] * 768, project="repo", doc_types={"code"}, limit=5)

    assert document_store.requested_ids == [doc_id]
    assert results == [
        {
            "id": doc_id,
            "title": "real-title",
            "path": "/repo/app.py",
            "content": "print('hello')",
            "score": 0.91,
            "doc_type": "code",
        }
    ]