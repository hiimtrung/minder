"""
Search & Graph Tool Handlers — MCP tool wrappers for search/graph operations.

Extracted from bootstrap/transport.py to respect Single Responsibility.
"""

from __future__ import annotations

from typing import Any

from minder.auth.principal import ClientPrincipal, Principal
from minder.domain.exceptions import AuthError
from minder.bootstrap.handlers.authorization import ensure_client_repo_access
from minder.tools.graph import GraphTools
from minder.tools.query import QueryTools


def create_search_handlers(
    query_tools: QueryTools,
    graph_tools: GraphTools,
) -> dict[str, Any]:
    """Return a dict of {tool_name: handler_fn} for search/graph MCP tools."""

    async def minder_search_code(
        *,
        user=None,
        principal: Principal | None = None,
        query: str,
        repo_path: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        if user is None and principal is None:
            raise AuthError("AUTH_MISSING_TOKEN", "Authenticated principal required")
        ensure_client_repo_access(principal, repo_path=repo_path)
        return await query_tools.minder_search_code(
            query, repo_path=repo_path, limit=limit
        )

    async def minder_search_errors(
        *, user=None, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_errors(query, limit=limit)

    async def minder_search_graph(
        *,
        user=None,
        principal: Principal | None = None,
        query: str,
        repo_path: str,
        node_types: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:  # noqa: ANN001
        if user is None and principal is None:
            raise AuthError("AUTH_MISSING_TOKEN", "Authenticated principal required")
        ensure_client_repo_access(principal, repo_path=repo_path)
        return await graph_tools.minder_search_graph(
            query,
            repo_path=repo_path,
            node_types=node_types,
            limit=limit,
            include_linked_repos=True,
            allowed_repo_scopes=(
                principal.repo_scope if isinstance(principal, ClientPrincipal) else None
            ),
        )

    async def minder_find_impact(
        *,
        user=None,
        principal: Principal | None = None,
        target: str,
        repo_path: str,
        depth: int = 2,
        limit: int = 25,
    ) -> dict[str, Any]:  # noqa: ANN001
        if user is None and principal is None:
            raise AuthError("AUTH_MISSING_TOKEN", "Authenticated principal required")
        ensure_client_repo_access(principal, repo_path=repo_path)
        return await graph_tools.minder_find_impact(
            target,
            repo_path=repo_path,
            depth=depth,
            limit=limit,
            include_linked_repos=True,
            allowed_repo_scopes=(
                principal.repo_scope if isinstance(principal, ClientPrincipal) else None
            ),
        )

    return {
        "minder_search_code": minder_search_code,
        "minder_search_errors": minder_search_errors,
        "minder_search_graph": minder_search_graph,
        "minder_find_impact": minder_find_impact,
    }
