"""
Auth Tool Handlers — MCP tool wrappers for authentication operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
Each handler is a thin presentation adapter that delegates to AuthTools.
"""

from __future__ import annotations

from typing import Any

from minder.auth.principal import Principal
from minder.domain.exceptions import AuthError
from minder.bootstrap.handlers.authorization import require_admin_user
from minder.tools.auth import AuthTools


def create_auth_handlers(auth_tools: AuthTools) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for auth-related MCP tools."""

    async def minder_auth_ping(message: str, *, user=None) -> dict[str, Any]:  # noqa: ANN001
        del user
        return {
            "status": f"auth pong: {message}",
            "_startup_sequence": [
                "STEP 1 — session: minder_session_find(name='<project-slug>') to recover prior context.",
                "  → Found: cache session_id, go to STEP 3.",
                "  → Not found: minder_session_create(name='<project-slug>'), cache session_id.",
                "  → SHORTCUT: minder_session_boot(project_name='<project-slug>') does STEP 1 in one call.",
                "STEP 2 — identity: minder_auth_whoami() to verify principal and available scopes.",
                "STEP 3 — workflow: minder_workflow_step(repo_id=<uuid>, repo_path=<path>) to get current_step.",
                "  → Find repo_id from minder://repos resource or session.project_context.",
                "STEP 4 — skills: minder_skill_recall(query='<task>', current_step='<step>') to load conventions.",
                "STEP 5 — memory: minder_memory_recall(query='<task>') to load project-specific decisions.",
            ],
            "_warning": (
                "auth_ping is for connectivity testing ONLY. "
                "Execute the startup sequence above immediately — do NOT fall back to generic tools."
            ),
        }

    async def minder_auth_login(api_key: str) -> dict[str, str]:
        return await auth_tools.minder_auth_login(api_key)

    async def minder_auth_exchange_client_key(
        client_api_key: str,
        requested_scopes: list[str] | None = None,
    ) -> dict[str, object]:
        return await auth_tools.minder_auth_exchange_client_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )

    async def minder_auth_whoami(
        *, user=None, principal: Principal | None = None
    ) -> dict[str, Any]:  # noqa: ANN001
        if user is not None:
            return {
                "principal_type": "user",
                "principal_id": str(user.id),
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "scopes": [],
                "repo_scope": [],
            }
        if principal is None:
            raise AuthError("AUTH_MISSING_TOKEN", "Authenticated principal required")
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "role": principal.role,
            "scopes": list(principal.scopes),
            "repo_scope": list(principal.repo_scope),
            "client_slug": getattr(principal, "client_slug", None),
        }

    async def minder_auth_manage(
        *, user=None, action: str
    ) -> dict[str, object]:  # noqa: ANN001
        authenticated_user = require_admin_user(user)
        return await auth_tools.minder_auth_manage(
            actor_user_id=authenticated_user.id, action=action
        )

    async def minder_auth_create_client(
        *,
        user=None,
        name: str,
        slug: str,
        description: str = "",
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
    ) -> dict[str, object]:  # noqa: ANN001
        authenticated_user = require_admin_user(user)
        return await auth_tools.minder_auth_create_client(
            actor_user_id=authenticated_user.id,
            name=name,
            slug=slug,
            description=description,
            tool_scopes=tool_scopes,
            repo_scopes=repo_scopes,
        )

    return {
        "minder_auth_ping": minder_auth_ping,
        "minder_auth_login": minder_auth_login,
        "minder_auth_exchange_client_key": minder_auth_exchange_client_key,
        "minder_auth_whoami": minder_auth_whoami,
        "minder_auth_manage": minder_auth_manage,
        "minder_auth_create_client": minder_auth_create_client,
    }


# Tool registration metadata: {tool_name: require_auth}
AUTH_TOOL_AUTH_REQUIREMENTS: dict[str, bool] = {
    "minder_auth_ping": True,
    "minder_auth_login": False,
    "minder_auth_exchange_client_key": False,
    "minder_auth_whoami": True,
    "minder_auth_manage": True,
    "minder_auth_create_client": True,
}
