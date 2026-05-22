"""
Skill Tool Handlers — MCP tool wrappers for skill operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

from typing import Any

from minder.tools.skills import SkillTools


def create_skill_handlers(skill_tools: SkillTools) -> dict[str, Any]:
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
        )

    async def minder_skill_recall(
        *,
        user=None,
        query: str,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        min_quality_score: float = 0.0,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_recall(
            query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            min_quality_score=min_quality_score,
        )

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

    async def minder_skill_update(
        *,
        user=None,
        skill_id: str,
        title: str | None = None,
        content: str | None = None,
        language: str | None = None,
        tags: list[str] | None = None,
        workflow_steps: list[str] | None = None,
        artifact_types: list[str] | None = None,
        provenance: str | None = None,
        quality_score: float | None = None,
        deprecated: bool | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_update(
            skill_id,
            title=title,
            content=content,
            language=language,
            tags=tags,
            workflow_steps=workflow_steps,
            artifact_types=artifact_types,
            provenance=provenance,
            quality_score=quality_score,
            deprecated=deprecated,
        )

    async def minder_skill_delete(
        *, user=None, skill_id: str
    ) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_delete(skill_id)

    async def minder_skill_import_git(
        *,
        user=None,
        repo_url: str,
        source_path: str = "skills",
        ref: str | None = None,
        provider: str | None = None,
        excerpt_kind: str = "none",
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await skill_tools.minder_skill_import_git(
            repo_url=repo_url,
            source_path=source_path,
            ref=ref,
            provider=provider,
            excerpt_kind=excerpt_kind,
        )

    return {
        "minder_skill_store": minder_skill_store,
        "minder_skill_recall": minder_skill_recall,
        "minder_skill_list": minder_skill_list,
        "minder_skill_update": minder_skill_update,
        "minder_skill_delete": minder_skill_delete,
        "minder_skill_import_git": minder_skill_import_git,
    }
