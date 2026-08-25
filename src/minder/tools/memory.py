from __future__ import annotations

import uuid
from typing import Any

from minder.config import MinderConfig
from minder.domain.interfaces.embedding import IEmbeddingProvider
from minder.store.interfaces import IOperationalStore
from minder.application.memory.service import (
    MEMORY_LANGUAGES as MEMORY_LANGUAGES,
    MemoryService,
    is_memory_record as is_memory_record,
)


class MemoryTools:
    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        *,
        embedder: IEmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._service = MemoryService(store=store, config=config, embedder=embedder)

    @property
    def _embedder(self) -> IEmbeddingProvider:
        return self._service._embedder

    def _get_synthesizer(self) -> Any:
        return self._service._get_synthesizer()

    def _use_agentic_loop(self) -> bool:
        return self._service._use_agentic_loop()

    def _get_agentic_graph(self) -> Any:
        return self._service._get_agentic_graph()

    async def _agentic_recall(
        self,
        query: str,
        *,
        limit: int,
        current_step: str | None,
        artifact_type: str | None,
        owner_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        return await self._service._agentic_recall(
            query=query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            owner_id=owner_id,
        )

    async def _recall_candidates(
        self,
        query: str,
        *,
        limit: int,
        current_step: str | None,
        artifact_type: str | None,
        include_raw_scores: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        return await self._service._recall_candidates(
            query=query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            include_raw_scores=include_raw_scores,
            owner_id=owner_id,
        )

    async def minder_memory_store(
        self,
        *,
        title: str,
        content: str,
        tags: list[str],
        language: str,
        owner_id: uuid.UUID | None = None,
        scope: str = "private",
        memory_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new memory entry, or update an existing one when ``memory_id`` is supplied."""
        if memory_id is not None:
            return await self._service.minder_memory_update(
                memory_id,
                title=title,
                content=content,
                tags=tags,
                owner_id=owner_id,
            )
        return await self._service.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
            owner_id=owner_id,
            scope=scope,
        )

    async def minder_memory_recall(
        self,
        query: str,
        *,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        skip_synthesis: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        return await self._service.minder_memory_recall(
            query=query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            skip_synthesis=skip_synthesis,
            owner_id=owner_id,
        )

    async def minder_memory_list(
        self,
        *,
        owner_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        return await self._service.minder_memory_list(owner_id=owner_id)

    async def minder_memory_update(
        self,
        memory_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_memory_update(
            memory_id=memory_id,
            title=title,
            content=content,
            tags=tags,
            owner_id=owner_id,
        )

    async def minder_memory_delete(
        self,
        memory_id: str,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, bool]:
        return await self._service.minder_memory_delete(
            memory_id=memory_id,
            owner_id=owner_id,

    async def minder_memory_compact(
        self,
        *,
        memory_ids: list[str],
        similarity_threshold: float = 0.92,
        dry_run: bool = True,
        owner_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_memory_compact(
            memory_ids=memory_ids,
            similarity_threshold=similarity_threshold,
            dry_run=dry_run,
            owner_id=owner_id,
        )
