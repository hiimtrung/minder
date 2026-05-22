"""
Session Tool Handlers — MCP tool wrappers for session lifecycle.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

import uuid
from typing import Any

from minder.auth.principal import ClientPrincipal, Principal
from minder.bootstrap.handlers.authorization import (
    require_authenticated_user,
    resolve_repo_uuid,
)
from minder.domain.interfaces.repositories import IOperationalStore
from minder.tools.session import SessionTools


def create_session_handlers(
    session_tools: SessionTools,
    store: IOperationalStore,
) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for session-related MCP tools."""

    async def minder_session_create(
        *,
        user=None,  # noqa: ANN001
        principal: Principal | None = None,
        name: str | None = None,
        repo_id: str | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_repo_id = await resolve_repo_uuid(repo_id, store) if repo_id else None
        if isinstance(principal, ClientPrincipal):
            return await session_tools.minder_session_create(
                client_id=principal.client_id,
                name=name,
                repo_id=resolved_repo_id,
                project_context=project_context,
            )
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_create(
            user_id=authenticated_user.id,
            name=name,
            repo_id=resolved_repo_id,
            project_context=project_context,
        )

    async def minder_session_find(
        *,
        user=None,  # noqa: ANN001
        principal: Principal | None = None,
        name: str,
    ) -> dict[str, Any]:
        if isinstance(principal, ClientPrincipal):
            return await session_tools.minder_session_find(
                name=name,
                client_id=principal.client_id,
            )
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_find(
            name=name,
            user_id=authenticated_user.id,
        )

    async def minder_session_list(
        *,
        user=None,  # noqa: ANN001
        principal: Principal | None = None,
    ) -> dict[str, Any]:
        if isinstance(principal, ClientPrincipal):
            return await session_tools.minder_session_list(
                client_id=principal.client_id
            )
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_list(user_id=authenticated_user.id)

    async def minder_session_save(
        *,
        user=None,
        session_id: str,
        state: dict[str, Any] | None = None,
        active_skills: dict[str, Any] | None = None,  # noqa: ANN001
        repo_id: str | None = None,
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
            repo_id=await resolve_repo_uuid(repo_id, store) if repo_id else None,
        )

    async def minder_session_restore(
        *, user=None, session_id: str
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_restore(uuid.UUID(session_id))

    async def minder_session_context(
        *,
        user=None,
        session_id: str,
        branch: str,
        open_files: list[str],  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_context(
            uuid.UUID(session_id),
            branch=branch,
            open_files=open_files,
        )

    async def minder_session_summarize(
        *, user=None, session_id: str
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_summarize(uuid.UUID(session_id))

    async def minder_session_cleanup(
        *,
        user=None,
        principal: Principal | None = None,
    ) -> dict[str, int]:
        if isinstance(principal, ClientPrincipal):
            return await session_tools.minder_session_cleanup(
                client_id=principal.client_id
            )
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_cleanup(user_id=authenticated_user.id)

    return {
        "minder_session_create": minder_session_create,
        "minder_session_find": minder_session_find,
        "minder_session_list": minder_session_list,
        "minder_session_save": minder_session_save,
        "minder_session_restore": minder_session_restore,
        "minder_session_context": minder_session_context,
        "minder_session_summarize": minder_session_summarize,
        "minder_session_cleanup": minder_session_cleanup,
    }
