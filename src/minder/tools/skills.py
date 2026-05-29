from __future__ import annotations

from typing import Any
from collections.abc import Awaitable, Callable

from minder.config import MinderConfig
from minder.domain.interfaces.embedding import IEmbeddingProvider
from minder.store.interfaces import IOperationalStore
from minder.application.skills.service import SkillService


class SkillTools:
    _ARTIFACT_TAGS = SkillService._ARTIFACT_TAGS

    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        *,
        embedder: IEmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._service = SkillService(store=store, config=config, embedder=embedder)

    async def minder_skill_store(
        self,
        *,
        title: str,
        content: str,
        language: str,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float = 0.0,
        source_metadata: dict[str, Any] | None = None,
        excerpt_kind: str = "none",
    ) -> dict[str, Any]:
        return await self._service.minder_skill_store(
            title=title,
            content=content,
            language=language,
            tags=tags,
            workflow_steps=workflow_steps,
            artifact_types=artifact_types,
            provenance=provenance,
            quality_score=quality_score,
            source_metadata=source_metadata,
            excerpt_kind=excerpt_kind,
        )

    async def minder_skill_recall(
        self,
        query: str,
        *,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        return await self._service.minder_skill_recall(
            query=query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            min_quality_score=min_quality_score,
        )

    async def minder_skill_recall_with_summary(
        self,
        query: str,
        *,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        min_quality_score: float = 0.0,
    ) -> tuple[list[dict[str, Any]], str]:
        return await self._service.minder_skill_recall_with_summary(
            query=query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            min_quality_score=min_quality_score,
        )

    async def minder_skill_list(
        self,
        *,
        current_step: str | None = None,
        tag: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        return await self._service.minder_skill_list(
            current_step=current_step,
            tag=tag,
            min_quality_score=min_quality_score,
        )

    async def minder_skill_update(
        self,
        skill_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float | None = None,
        deprecated: bool | None = None,
        source_metadata: dict[str, Any] | None = None,
        excerpt_kind: str | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_skill_update(
            skill_id=skill_id,
            title=title,
            content=content,
            language=language,
            tags=tags,
            workflow_steps=workflow_steps,
            artifact_types=artifact_types,
            provenance=provenance,
            quality_score=quality_score,
            deprecated=deprecated,
            source_metadata=source_metadata,
            excerpt_kind=excerpt_kind,
        )

    async def minder_skill_import_git(
        self,
        *,
        repo_url: str,
        source_path: str = "skills",
        ref: str | None = None,
        provider: str | None = None,
        excerpt_kind: str = "none",
        progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        return await self._service.minder_skill_import_git(
            repo_url=repo_url,
            source_path=source_path,
            ref=ref,
            provider=provider,
            excerpt_kind=excerpt_kind,
            progress_callback=progress_callback,
        )

    async def minder_skill_delete(self, skill_id: str) -> dict[str, bool]:
        return await self._service.minder_skill_delete(skill_id=skill_id)
