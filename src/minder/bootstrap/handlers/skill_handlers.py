"""
Skill Tool Handlers — MCP tool wrappers for skill operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from minder.domain.interfaces.repositories import IOperationalStore
from minder.tools.skills import SkillTools

logger = logging.getLogger(__name__)


def create_skill_handlers(
    skill_tools: SkillTools,
    store: IOperationalStore | None = None,
) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for skill-related MCP tools."""

    async def minder_skill_store(
        *,
        user=None,
        title: str,
        content: str,
        language: str,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float = 0.0,
        skill_id: str | None = None,
        deprecated: bool | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_store(
            title=title,
            content=content,
            language=language,
            tags=tags,
            workflow_steps=workflow_steps,
            artifact_types=artifact_types,
            provenance=provenance,
            quality_score=quality_score,
            skill_id=skill_id,
            deprecated=deprecated,
        )

    async def minder_skill_recall(
        *,
        user=None,
        query: str,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        min_quality_score: float = 0.0,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        results, summary = await skill_tools.minder_skill_recall_with_summary(
            query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            min_quality_score=min_quality_score,
        )
        if session_id and results and store is not None:
            try:
                sid = uuid.UUID(session_id)
                titles = ", ".join(r.get("title", "") for r in results[:3] if r.get("title"))
                history_content = summary or f"Recalled {len(results)} skills for '{query}': {titles}."
                await store.create_history(session_id=sid, role="user", content=query)
                await store.create_history(session_id=sid, role="assistant", content=history_content)
            except Exception as exc:
                logger.debug("minder_skill_recall: failed to persist history: %s", exc)
        return results

    async def minder_skill_list(
        *,
        user=None,
        current_step: str | None = None,
        tag: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_list(
            current_step=current_step,
            tag=tag,
            min_quality_score=min_quality_score,
        )

    async def minder_skill_delete(
        *, user=None, skill_id: str
    ) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_delete(skill_id)

    async def minder_skill_curate(
        *,
        user=None,
        session_id: str,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_curate(session_id=session_id)

    async def minder_skill_review(
        *,
        user=None,
        action: str,
        skill_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_review(
            action=action,
            skill_id=skill_id,
            title=title,
            content=content,
        )

    return {
        "minder_skill_store": minder_skill_store,
        "minder_skill_recall": minder_skill_recall,
        "minder_skill_list": minder_skill_list,
        "minder_skill_delete": minder_skill_delete,
        "minder_skill_curate": minder_skill_curate,
        "minder_skill_review": minder_skill_review,
    }
