from __future__ import annotations

import base64
from typing import Any

import pytest

from minder.graph.checkpoint import MinderCheckpointSaver


class FakeQdrantCheckpointStore:
    def __init__(self) -> None:
        self.record: dict[str, Any] | None = None

    async def get_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        if self.record and self.record["thread_id"] == thread_id:
            return self.record
        return None

    async def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        checkpoint: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.record = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint_b64": base64.b64encode(checkpoint).decode(),
            "metadata": metadata or {},
        }

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        del limit
        if self.record and self.record["thread_id"] == thread_id:
            return [self.record]
        return []


@pytest.mark.asyncio
async def test_checkpoint_saver_reads_qdrant_base64_payloads() -> None:
    store = FakeQdrantCheckpointStore()
    saver = MinderCheckpointSaver(store)  # type: ignore[arg-type]
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    checkpoint = {
        "id": "checkpoint-1",
        "channel_values": {"messages": ["hello"]},
        "channel_versions": {"messages": 1},
        "versions_seen": {"node": {"messages": 1}},
        "pending_sends": [],
    }
    metadata = {"source": "test"}

    await saver.aput(config, checkpoint, metadata, {})

    restored = await saver.aget_tuple(config)

    assert restored is not None
    assert restored.checkpoint == checkpoint
    assert restored.metadata == metadata
