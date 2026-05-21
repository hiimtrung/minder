from __future__ import annotations

from types import SimpleNamespace

import pytest

from minder.store.qdrant.operational_store import QdrantOperationalStore


class FakeCheckpointCollection:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict[str, object]]] = []

    async def find_one(self, field: str, value: object):
        assert field == "thread_id"
        assert value == "thread-1"
        return SimpleNamespace(id="checkpoint-doc-id")

    async def set_payload(self, point_id: str, payload: dict[str, object]) -> None:
        self.updated.append((point_id, payload))

    async def update(self, point_id: str, updates: dict[str, object]):
        raise AssertionError("checkpoint saves should not call CollectionCRUD.update")

    async def insert(self, payload: dict[str, object], point_id: str) -> None:
        raise AssertionError("existing checkpoint should not insert a new record")


@pytest.mark.asyncio
async def test_qdrant_checkpoint_save_skips_read_before_write() -> None:
    store = QdrantOperationalStore(SimpleNamespace(client=object(), prefix="test_"))
    collection = FakeCheckpointCollection()
    store._collections["test_checkpoints"] = collection  # type: ignore[assignment]

    await store.save_checkpoint(
        thread_id="thread-1",
        checkpoint_id="checkpoint-2",
        checkpoint=b"payload-bytes",
        metadata={"source": "test"},
    )

    assert collection.updated == [
        (
            "checkpoint-doc-id",
            {
                "thread_id": "thread-1",
                "checkpoint_id": "checkpoint-2",
                "checkpoint_b64": "cGF5bG9hZC1ieXRlcw==",
                "metadata": {"source": "test"},
            },
        )
    ]
