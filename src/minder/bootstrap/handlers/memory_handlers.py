"""
Memory Tool Handlers — MCP tool wrappers for memory operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from minder.auth.principal import Principal
from minder.bootstrap.handlers.authorization import extract_owner_id
from minder.domain.interfaces.repositories import IOperationalStore
from minder.tools.memory import MemoryTools

logger = logging.getLogger(__name__)


def create_memory_handlers(
    memory_tools: MemoryTools,
    store: IOperationalStore | None = None,
) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for memory-related MCP tools."""

    async def minder_memory_store(
        *,
        user=None,
        principal: Principal | None = None,
        title: str,
        content: str,
        tags: list[str],
        language: str,
        scope: str = "private",
        memory_id: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
            owner_id=owner_id,
            scope=scope,
            memory_id=memory_id,
        )

    async def minder_memory_recall(
        *,
        user=None,
        principal: Principal | None = None,
        query: str,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        results = await memory_tools.minder_memory_recall(
            query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
            owner_id=owner_id,
        )
        if session_id and results and store is not None:
            try:
                sid = uuid.UUID(session_id)
                summaries = [r.get("hit_summary") or r.get("title", "") for r in results[:3]]
                history_content = f"Recalled {len(results)} memories for '{query}': " + "; ".join(s for s in summaries if s) + "."
                await store.create_history(session_id=sid, role="user", content=query)
                await store.create_history(session_id=sid, role="assistant", content=history_content)
            except Exception as exc:
                logger.debug("minder_memory_recall: failed to persist history: %s", exc)
        return results

    async def minder_memory_list(
        *,
        user=None,
        principal: Principal | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_list(owner_id=owner_id)

    async def minder_memory_delete(
        *, user=None, principal: Principal | None = None, memory_id: str
        owner_id = extract_owner_id(principal=principal, user=user)
        return await memory_tools.minder_memory_delete(memory_id, owner_id=owner_id)

        "minder_memory_store": minder_memory_store,
        "minder_memory_recall": minder_memory_recall,
        "minder_memory_list": minder_memory_list,
        "minder_memory_delete": minder_memory_delete,
    }
