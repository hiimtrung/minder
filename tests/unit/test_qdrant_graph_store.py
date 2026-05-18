from __future__ import annotations

from types import MethodType, SimpleNamespace
import uuid

import pytest

from minder.store.qdrant.graph_store import QdrantGraphStore


class FakeBatchCollection:
    def __init__(self, existing_docs: list[SimpleNamespace]) -> None:
        self.existing_docs = existing_docs
        self.find_many_calls: list[tuple[dict[str, object], int]] = []
        self.upsert_many_calls: list[list[tuple[str, dict[str, object]]]] = []

    async def find_many(
        self,
        filters: dict[str, object] | None = None,
        *,
        limit: int = 1000,
        offset: int = 0,
        order_field: str | None = None,
        order_desc: bool = True,
    ) -> list[SimpleNamespace]:
        del offset, order_field, order_desc
        self.find_many_calls.append((filters or {}, limit))
        return self.existing_docs

    async def upsert_many(
        self,
        records: list[tuple[str, dict[str, object]]],
    ) -> list[SimpleNamespace]:
        self.upsert_many_calls.append(records)
        return [
            SimpleNamespace(id=uuid.UUID(point_id), _data=payload)
            for point_id, payload in records
        ]


@pytest.mark.asyncio
async def test_bulk_upsert_nodes_batches_qdrant_writes() -> None:
    existing_id = uuid.uuid4()
    existing_doc = SimpleNamespace(
        id=existing_id,
        _data={
            "node_type": "service",
            "name": "billing",
            "extra_metadata": {"path": "old.py", "owner": "payments"},
            "created_at": "2026-05-18T10:00:00+00:00",
        },
    )
    store = QdrantGraphStore(SimpleNamespace(client=object(), prefix="test_"))
    store._nodes = FakeBatchCollection([existing_doc])  # type: ignore[assignment]

    async def fail_upsert_node(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("bulk_upsert_nodes should not call upsert_node")

    store.upsert_node = MethodType(fail_upsert_node, store)

    id_map = await store.bulk_upsert_nodes(
        [
            {
                "node_type": "service",
                "name": "billing",
                "metadata": {"path": "new.py", "team": "platform"},
            },
            {
                "node_type": "module",
                "name": "billing.api",
                "metadata": {"path": "api.py"},
            },
        ],
        repo_id="repo-1",
        branch="main",
    )

    assert store._nodes.find_many_calls == [
        ({"repo_id": "repo-1", "branch": "main"}, 9000)
    ]
    assert len(store._nodes.upsert_many_calls) == 1
    batched = store._nodes.upsert_many_calls[0]
    assert len(batched) == 2
    assert batched[0][0] == str(existing_id)
    assert batched[0][1]["extra_metadata"] == {
        "path": "new.py",
        "owner": "payments",
        "team": "platform",
    }
    assert batched[0][1]["created_at"] == "2026-05-18T10:00:00+00:00"
    assert id_map[("service", "billing")] == existing_id
    assert id_map[("module", "billing.api")]


@pytest.mark.asyncio
async def test_bulk_upsert_edges_batches_qdrant_writes() -> None:
    existing_edge_id = uuid.uuid4()
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    existing_doc = SimpleNamespace(
        id=existing_edge_id,
        _data={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation": "calls",
            "created_at": "2026-05-18T10:01:00+00:00",
        },
    )
    store = QdrantGraphStore(SimpleNamespace(client=object(), prefix="test_"))
    store._edges = FakeBatchCollection([existing_doc])  # type: ignore[assignment]

    async def fail_upsert_edge(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("bulk_upsert_edges should not call upsert_edge")

    store.upsert_edge = MethodType(fail_upsert_edge, store)

    count = await store.bulk_upsert_edges(
        [
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation": "calls",
                "weight": 2.0,
            },
            {
                "source_id": target_id,
                "target_id": source_id,
                "relation": "depends_on",
                "weight": 1.0,
            },
        ],
        repo_id="repo-1",
    )

    assert count == 2
    assert store._edges.find_many_calls == [({"repo_id": "repo-1"}, 9000)]
    assert len(store._edges.upsert_many_calls) == 1
    batched = store._edges.upsert_many_calls[0]
    assert len(batched) == 2
    assert batched[0][0] == str(existing_edge_id)
    assert batched[0][1]["weight"] == 2.0
    assert batched[0][1]["created_at"] == "2026-05-18T10:01:00+00:00"
