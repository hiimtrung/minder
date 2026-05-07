from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
import zlib
from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langchain_core.runnables import RunnableConfig

from minder.store.interfaces import IOperationalStore


class MinderCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, store: IOperationalStore) -> None:
        super().__init__()
        self._store = store

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            return None

        # Check if the store implements ICheckpointRepository
        if not hasattr(self._store, "get_checkpoint"):
            return None

        data = await self._store.get_checkpoint(thread_id)
        if data is None:
            return None

        metadata = data.get("metadata", {})
        type_name = metadata.pop("_checkpoint_type", "msgpack")
        payload = bytes(data["checkpoint"])
        if metadata.pop("_checkpoint_compression", None) == "zlib":
            payload = zlib.decompress(payload)
        checkpoint = self.serde.loads_typed((type_name, payload))
        
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=None,  # We don't track full history trees in simple setup
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | float | int],
    ) -> RunnableConfig:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            return config

        if not hasattr(self._store, "save_checkpoint"):
            return config

        type_name, payload = self.serde.dumps_typed(checkpoint)
        payload = zlib.compress(payload)
        db_metadata = dict(metadata or {})
        db_metadata["_checkpoint_type"] = type_name
        db_metadata["_checkpoint_compression"] = "zlib"

        await self._store.save_checkpoint(
            thread_id=thread_id,
            checkpoint_id=checkpoint["id"],
            checkpoint=payload,
            metadata=db_metadata,
        )
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": configurable.get("checkpoint_ns", ""),
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncGenerator[CheckpointTuple, None]:
        if config is None:
            return
            
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            return

        if not hasattr(self._store, "list_checkpoints"):
            return

        records = await self._store.list_checkpoints(thread_id, limit=limit or 10)
        for record in records:
            metadata = record.get("metadata", {})
            type_name = metadata.pop("_checkpoint_type", "msgpack")
            payload = bytes(record["checkpoint"])
            if metadata.pop("_checkpoint_compression", None) == "zlib":
                payload = zlib.decompress(payload)
            checkpoint = self.serde.loads_typed((type_name, payload))
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": configurable.get("checkpoint_ns", ""),
                        "checkpoint_id": record["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
            )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        # We only persist full checkpoints for Minder's workflow right now.
        # LangGraph requires this method, but for simple state sync it can be a no-op
        # unless fine-grained node-level recovery is needed.
        pass

    # Note: Sync versions of these methods must be implemented but can just raise NotImplementedError
    # since we only use async langgraph execution (`ainvoke`).

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise NotImplementedError("MinderCheckpointSaver only supports async.")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, str | float | int],
    ) -> RunnableConfig:
        raise NotImplementedError("MinderCheckpointSaver only supports async.")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ):
        raise NotImplementedError("MinderCheckpointSaver only supports async.")
