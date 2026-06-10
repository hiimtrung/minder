"""
Auth Tool Handlers — MCP tool wrappers for authentication operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
Each handler is a thin presentation adapter that delegates to AuthTools.
"""

from __future__ import annotations

from typing import Any

from minder.auth.principal import Principal
from minder.domain.exceptions import AuthError
from minder.tools.auth import AuthTools


def create_auth_handlers(auth_tools: AuthTools) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for auth-related MCP tools."""

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
        _startup_sequence = [
            "minder_session_boot is ALWAYS AVAILABLE — call it next regardless of scopes listed here.",
            "minder_session_boot(project_name='<project-slug>', project_context={'repo_path': '<abs-path>'}) — find-or-create session in one call.",
            "After boot: PARALLEL minder_workflow_step(repo_id=...) + minder_skill_recall(query='<task>').",
            "Read minder://instructions for the complete sequencing guide.",
        ]
        if user is not None:
            return {
                "principal_type": "user",
                "principal_id": str(user.id),
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "scopes": [],
                "repo_scope": [],
                "_startup_sequence": _startup_sequence,
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
            "_startup_sequence": _startup_sequence,
        }

    return {
        "minder_auth_login": minder_auth_login,
        "minder_auth_exchange_client_key": minder_auth_exchange_client_key,
        "minder_auth_whoami": minder_auth_whoami,
    }


# Tool registration metadata: {tool_name: require_auth}
AUTH_TOOL_AUTH_REQUIREMENTS: dict[str, bool] = {
    "minder_auth_login": False,
    "minder_auth_exchange_client_key": False,
    "minder_auth_whoami": True,
}
