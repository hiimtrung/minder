"""
Memory Tool Handlers — MCP tool wrappers for memory operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

from typing import Any

from minder.auth.principal import Principal
from minder.bootstrap.handlers.authorization import extract_owner_id
from minder.tools.memory import MemoryTools


def create_memory_handlers(memory_tools: MemoryTools) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for memory-related MCP tools."""

    async def minder_memory_store(
        *,
        user=None,
        principal: Principal | None = None,
        title: str,
        content: str,
        tags: list[str],
        language: str,  # noqa: ANN001
        scope: str = "private",
    ) -> dict[str, Any]:
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
            owner_id=owner_id,
            scope=scope,
        )

    async def minder_memory_recall(
        *,
        user=None,
        principal: Principal | None = None,
        query: str,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_recall(
            query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            owner_id=owner_id,
        )

    async def minder_memory_list(
        *,
        user=None,
        principal: Principal | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_list(owner_id=owner_id)

    async def minder_memory_update(
        *,
        user=None,
        principal: Principal | None = None,
        memory_id: str,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_update(
            memory_id,
            title=title,
            content=content,
            tags=tags,
            owner_id=owner_id,
        )

    async def minder_memory_delete(
        *, user=None, principal: Principal | None = None, skill_id: str
    ) -> dict[str, bool]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_delete(skill_id, owner_id=owner_id)

    async def minder_memory_compact(
        *,
        user=None,
        principal: Principal | None = None,
        memory_ids: list[str],
        similarity_threshold: float = 0.92,
        dry_run: bool = True,
    ) -> dict[str, Any]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_compact(
            memory_ids=memory_ids,
            similarity_threshold=similarity_threshold,
            dry_run=dry_run,
            owner_id=owner_id,
        )

    return {
        "minder_memory_store": minder_memory_store,
        "minder_memory_recall": minder_memory_recall,
        "minder_memory_list": minder_memory_list,
        "minder_memory_update": minder_memory_update,
        "minder_memory_delete": minder_memory_delete,
        "minder_memory_compact": minder_memory_compact,
    }
