from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from minder.auth.principal import ClientPrincipal, Principal
from minder.auth.service import AuthError
from minder.auth.service import AuthService
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.presentation.http.admin.routes import build_http_routes
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry
from minder.store.interfaces import (
    ICacheProvider,
    IGraphRepository,
    IOperationalStore,
    IVectorStore,
)
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.graph import GraphTools
from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.registry import TOOL_DESCRIPTIONS
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools
from minder.transport import SSETransport, StdioTransport


def build_transport(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    vector_store: IVectorStore,
    graph_store: IGraphRepository | None = None,
    cache: ICacheProvider | None = None,
) -> SSETransport | StdioTransport:
    auth_service = AuthService(store, config, cache=cache)
    cache_provider = cache or LRUCacheProvider()
    repo_state_store = RepoStateStore(config.workflow.repo_state_dir)
    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    search_tools = SearchTools(store, config)
    graph_tools = GraphTools(graph_store, store)
    query_tools = QueryTools(
        store,
        config,
        vector_store=vector_store,
        graph_tools=graph_tools,
    )

    transport: SSETransport | StdioTransport
    if config.server.transport == "stdio":
        transport = StdioTransport(
            config=config,
            auth_service=auth_service,
            cache_provider=cache_provider,
            store=store,
        )
    else:
        transport = SSETransport(
            config=config,
            store=store,
            auth_service=auth_service,
            extra_routes=[],
            cache_provider=cache_provider,
        )

        async def sync_prompts() -> None:
            await PromptRegistry.sync(transport.app, store)

        transport.extend_routes(
            build_http_routes(
                config=config,
                store=store,
                graph_store=graph_store,
                cache=cache,
                prompt_sync_hook=sync_prompts,
            )
        )

    def ensure_client_repo_access(
        principal: Principal | None,
        *,
        repo_path: str,
    ) -> None:
        if not isinstance(principal, ClientPrincipal):
            return
        scopes = [
            scope.strip().rstrip("/")
            for scope in principal.repo_scope
            if scope and scope.strip()
        ]
        repo_root = Path(repo_path).resolve()
        candidates = {repo_path.rstrip("/"), str(repo_root).rstrip("/"), repo_root.name}
        if not scopes or (
            "*" not in scopes
            and not any(
                any(
                    candidate == scope or candidate.startswith(f"{scope}/")
                    for candidate in candidates
                )
                for scope in scopes
            )
        ):
            raise AuthError(
                "AUTH_FORBIDDEN", "Client is not allowed to inspect this repository"
            )

    def require_authenticated_user(user: Any | None) -> Any:
        if user is None:
            raise AuthError("AUTH_FORBIDDEN", "Authenticated user required")
        return user

    def require_admin_user(user: Any | None) -> Any:
        authenticated_user = require_authenticated_user(user)
        if getattr(authenticated_user, "role", None) != "admin":
            raise AuthError("AUTH_FORBIDDEN", "Admin role required")
        return authenticated_user

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

    async def minder_session_create(
        *,
        user=None,  # noqa: ANN001
        principal: Principal | None = None,
        name: str | None = None,
        repo_id: str | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if isinstance(principal, ClientPrincipal):
            return await session_tools.minder_session_create(
                client_id=principal.client_id,
                name=name,
                repo_id=uuid.UUID(repo_id) if repo_id else None,
                project_context=project_context,
            )
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_create(
            user_id=authenticated_user.id,
            name=name,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
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
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
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

    async def minder_workflow_get(
        *, user=None, repo_id: str, repo_path: str
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_get(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_step(
        *, user=None, repo_id: str, repo_path: str
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_step(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_update(
        *,
        user=None,
        repo_id: str,
        repo_path: str,
        completed_step: str,
        artifact_name: str | None = None,
        artifact_content: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_update(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
            completed_step=completed_step,
            artifact_name=artifact_name,
            artifact_content=artifact_content,
        )

    async def minder_workflow_guard(
        *, user=None, repo_id: str, requested_step: str, action: str | None = None
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=uuid.UUID(repo_id),
            requested_step=requested_step,
            action=action,
        )

    async def minder_memory_store(
        *,
        user=None,
        title: str,
        content: str,
        tags: list[str],
        language: str,  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
        )

    async def minder_memory_recall(
        *,
        user=None,
        query: str,
        limit: int = 5,
        current_step: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_recall(
            query,
            limit=limit,
            current_step=current_step,
            artifact_type=artifact_type,
        )

    async def minder_memory_list(*, user=None) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_list()

    async def minder_memory_delete(
        *, user=None, skill_id: str
    ) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_delete(skill_id)

    async def minder_search(
        *, user=None, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await search_tools.minder_search(query, limit=limit)

    async def minder_query(
        *,
        user=None,
        principal: Principal | None = None,
        query: str,
        repo_path: str,
        session_id: str | None = None,
        repo_id: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        if user is None and principal is None:
            raise AuthError("AUTH_MISSING_TOKEN", "Authenticated principal required")
        ensure_client_repo_access(principal, repo_path=repo_path)
        return await query_tools.minder_query(
            query,
            repo_path=repo_path,
            session_id=uuid.UUID(session_id) if session_id else None,
            user_id=user.id if user else None,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            workflow_name=workflow_name,
            allowed_repo_scopes=(
                principal.repo_scope if isinstance(principal, ClientPrincipal) else None
            ),
        )

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

    async def minder_auth_ping(message: str, *, user=None) -> str:  # noqa: ANN001
        del user
        return f"auth pong: {message}"

    transport.register_tool(
        "minder_auth_ping",
        minder_auth_ping,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_ping"],
    )
    transport.register_tool(
        "minder_auth_login",
        minder_auth_login,
        require_auth=False,
        description=TOOL_DESCRIPTIONS["minder_auth_login"],
    )
    transport.register_tool(
        "minder_auth_exchange_client_key",
        minder_auth_exchange_client_key,
        require_auth=False,
        description=TOOL_DESCRIPTIONS["minder_auth_exchange_client_key"],
    )
    transport.register_tool(
        "minder_auth_whoami",
        minder_auth_whoami,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_whoami"],
    )
    transport.register_tool(
        "minder_auth_manage",
        minder_auth_manage,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_manage"],
    )
    transport.register_tool(
        "minder_auth_create_client",
        minder_auth_create_client,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_create_client"],
    )
    transport.register_tool(
        "minder_session_create",
        minder_session_create,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_create"],
    )
    transport.register_tool(
        "minder_session_find",
        minder_session_find,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_find"],
    )
    transport.register_tool(
        "minder_session_list",
        minder_session_list,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_list"],
    )
    transport.register_tool(
        "minder_session_save",
        minder_session_save,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_save"],
    )
    transport.register_tool(
        "minder_session_restore",
        minder_session_restore,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_restore"],
    )
    transport.register_tool(
        "minder_session_context",
        minder_session_context,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_session_context"],
    )
    transport.register_tool(
        "minder_workflow_get",
        minder_workflow_get,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_workflow_get"],
    )
    transport.register_tool(
        "minder_workflow_step",
        minder_workflow_step,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_workflow_step"],
    )
    transport.register_tool(
        "minder_workflow_update",
        minder_workflow_update,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_workflow_update"],
    )
    transport.register_tool(
        "minder_workflow_guard",
        minder_workflow_guard,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_workflow_guard"],
    )
    transport.register_tool(
        "minder_memory_store",
        minder_memory_store,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_memory_store"],
    )
    transport.register_tool(
        "minder_memory_recall",
        minder_memory_recall,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_memory_recall"],
    )
    transport.register_tool(
        "minder_memory_list",
        minder_memory_list,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_memory_list"],
    )
    transport.register_tool(
        "minder_memory_delete",
        minder_memory_delete,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_memory_delete"],
    )
    transport.register_tool(
        "minder_search",
        minder_search,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_search"],
    )
    transport.register_tool(
        "minder_query",
        minder_query,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_query"],
    )
    transport.register_tool(
        "minder_search_code",
        minder_search_code,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_search_code"],
    )
    transport.register_tool(
        "minder_search_errors",
        minder_search_errors,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_search_errors"],
    )
    transport.register_tool(
        "minder_search_graph",
        minder_search_graph,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_search_graph"],
    )
    transport.register_tool(
        "minder_find_impact",
        minder_find_impact,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_find_impact"],
    )

    ResourceRegistry.register(transport.app, store, graph_store=graph_store)
    PromptRegistry.register(transport.app, store=store)
    return transport
