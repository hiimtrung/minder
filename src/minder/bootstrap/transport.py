from __future__ import annotations

import uuid
from typing import Any

from minder.auth.principal import Principal
from minder.auth.service import AuthError
from minder.auth.service import AuthService
from minder.config import MinderConfig
from minder.presentation.http.admin.routes import build_http_routes
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry
from minder.store.interfaces import ICacheProvider, IOperationalStore, IVectorStore
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools
from minder.transport import SSETransport, StdioTransport


TOOL_DESCRIPTIONS: dict[str, str] = {
    "minder_auth_ping": "Verify that MCP authentication is working and the current principal can reach protected tools.",
    "minder_auth_login": "Exchange a human admin API key for a JWT bearer token.",
    "minder_auth_exchange_client_key": "Exchange a client API key for a scoped client access token.",
    "minder_auth_whoami": "Return the authenticated principal identity, role, and any active scopes.",
    "minder_auth_manage": "Run admin-only authentication management actions such as listing registered users.",
    "minder_auth_create_client": "Create a new MCP client and issue its initial client API key.",
    "minder_session_create": "Create a persisted Minder session for an authenticated human user.",
    "minder_session_save": "Persist state and active skill context for an existing Minder session.",
    "minder_session_restore": "Load the saved state and context for an existing Minder session.",
    "minder_session_context": "Update branch and open-file context for an existing Minder session.",
    "minder_workflow_get": "Fetch the workflow assigned to a repository and sync repo-state files.",
    "minder_workflow_step": "Return the current workflow step for a repository and sync repo-state files.",
    "minder_workflow_update": "Mark a workflow step complete and optionally persist an artifact for the repository.",
    "minder_workflow_guard": "Check whether a requested workflow step is currently allowed for the repository.",
    "minder_memory_store": "Store a memory entry with title, content, tags, and language metadata.",
    "minder_memory_recall": "Search stored memory entries by semantic similarity.",
    "minder_memory_list": "List the currently stored memory entries.",
    "minder_memory_delete": "Delete a stored memory entry by its ID.",
    "minder_search": "Search Minder knowledge and stored project context.",
    "minder_query": "Run a full Minder repository query with retrieval, reasoning, and verification.",
    "minder_search_code": "Search indexed repository code for relevant files and snippets.",
    "minder_search_errors": "Search indexed errors and troubleshooting history for relevant matches.",
}


def build_transport(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    vector_store: IVectorStore,
    cache: ICacheProvider | None = None,
) -> SSETransport | StdioTransport:
    auth_service = AuthService(store, config, cache=cache)
    repo_state_store = RepoStateStore(config.workflow.repo_state_dir)
    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    search_tools = SearchTools(store, config)
    query_tools = QueryTools(store, config, vector_store=vector_store)

    transport: SSETransport | StdioTransport
    if config.server.transport == "stdio":
        transport = StdioTransport(config=config, auth_service=auth_service, cache_provider=cache)
    else:
        transport = SSETransport(
            config=config,
            auth_service=auth_service,
            extra_routes=build_http_routes(config=config, store=store, cache=cache),
            cache_provider=cache,
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

    async def minder_auth_whoami(*, user=None, principal: Principal | None = None) -> dict[str, Any]:  # noqa: ANN001
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

    async def minder_auth_manage(*, user=None, action: str) -> dict[str, object]:  # noqa: ANN001
        authenticated_user = require_admin_user(user)
        return await auth_tools.minder_auth_manage(actor_user_id=authenticated_user.id, action=action)

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
        *, user=None, repo_id: str | None = None, project_context: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        authenticated_user = require_authenticated_user(user)
        return await session_tools.minder_session_create(
            user_id=authenticated_user.id,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            project_context=project_context,
        )

    async def minder_session_save(
        *, user=None, session_id: str, state: dict[str, Any] | None = None, active_skills: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
        )

    async def minder_session_restore(*, user=None, session_id: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_restore(uuid.UUID(session_id))

    async def minder_session_context(
        *, user=None, session_id: str, branch: str, open_files: list[str]  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_context(
            uuid.UUID(session_id),
            branch=branch,
            open_files=open_files,
        )

    async def minder_workflow_get(*, user=None, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_get(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_step(*, user=None, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
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

    async def minder_workflow_guard(*, user=None, repo_id: str, requested_step: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=uuid.UUID(repo_id),
            requested_step=requested_step,
        )

    async def minder_memory_store(
        *, user=None, title: str, content: str, tags: list[str], language: str  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
        )

    async def minder_memory_recall(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_recall(query, limit=limit)

    async def minder_memory_list(*, user=None) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_list()

    async def minder_memory_delete(*, user=None, skill_id: str) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_delete(skill_id)

    async def minder_search(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await search_tools.minder_search(query, limit=limit)

    async def minder_query(
        *,
        user=None,
        query: str,
        repo_path: str,
        session_id: str | None = None,
        repo_id: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        return await query_tools.minder_query(
            query,
            repo_path=repo_path,
            session_id=uuid.UUID(session_id) if session_id else None,
            user_id=user.id if user else None,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            workflow_name=workflow_name,
        )

    async def minder_search_code(*, user=None, query: str, repo_path: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_code(query, repo_path=repo_path, limit=limit)

    async def minder_search_errors(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_errors(query, limit=limit)

    async def minder_auth_ping(message: str, *, user=None) -> str:  # noqa: ANN001
        del user
        return f"auth pong: {message}"

    transport.register_tool(
        "minder_auth_ping",
        minder_auth_ping,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_ping"],
    )
    transport.register_tool("minder_auth_login", minder_auth_login, require_auth=False, description=TOOL_DESCRIPTIONS["minder_auth_login"])
    transport.register_tool(
        "minder_auth_exchange_client_key",
        minder_auth_exchange_client_key,
        require_auth=False,
        description=TOOL_DESCRIPTIONS["minder_auth_exchange_client_key"],
    )
    transport.register_tool("minder_auth_whoami", minder_auth_whoami, require_auth=True, description=TOOL_DESCRIPTIONS["minder_auth_whoami"])
    transport.register_tool("minder_auth_manage", minder_auth_manage, require_auth=True, description=TOOL_DESCRIPTIONS["minder_auth_manage"])
    transport.register_tool(
        "minder_auth_create_client",
        minder_auth_create_client,
        require_auth=True,
        description=TOOL_DESCRIPTIONS["minder_auth_create_client"],
    )
    transport.register_tool("minder_session_create", minder_session_create, require_auth=True, description=TOOL_DESCRIPTIONS["minder_session_create"])
    transport.register_tool("minder_session_save", minder_session_save, require_auth=True, description=TOOL_DESCRIPTIONS["minder_session_save"])
    transport.register_tool("minder_session_restore", minder_session_restore, require_auth=True, description=TOOL_DESCRIPTIONS["minder_session_restore"])
    transport.register_tool("minder_session_context", minder_session_context, require_auth=True, description=TOOL_DESCRIPTIONS["minder_session_context"])
    transport.register_tool("minder_workflow_get", minder_workflow_get, require_auth=True, description=TOOL_DESCRIPTIONS["minder_workflow_get"])
    transport.register_tool("minder_workflow_step", minder_workflow_step, require_auth=True, description=TOOL_DESCRIPTIONS["minder_workflow_step"])
    transport.register_tool("minder_workflow_update", minder_workflow_update, require_auth=True, description=TOOL_DESCRIPTIONS["minder_workflow_update"])
    transport.register_tool("minder_workflow_guard", minder_workflow_guard, require_auth=True, description=TOOL_DESCRIPTIONS["minder_workflow_guard"])
    transport.register_tool("minder_memory_store", minder_memory_store, require_auth=True, description=TOOL_DESCRIPTIONS["minder_memory_store"])
    transport.register_tool("minder_memory_recall", minder_memory_recall, require_auth=True, description=TOOL_DESCRIPTIONS["minder_memory_recall"])
    transport.register_tool("minder_memory_list", minder_memory_list, require_auth=True, description=TOOL_DESCRIPTIONS["minder_memory_list"])
    transport.register_tool("minder_memory_delete", minder_memory_delete, require_auth=True, description=TOOL_DESCRIPTIONS["minder_memory_delete"])
    transport.register_tool("minder_search", minder_search, require_auth=True, description=TOOL_DESCRIPTIONS["minder_search"])
    transport.register_tool("minder_query", minder_query, require_auth=True, description=TOOL_DESCRIPTIONS["minder_query"])
    transport.register_tool("minder_search_code", minder_search_code, require_auth=True, description=TOOL_DESCRIPTIONS["minder_search_code"])
    transport.register_tool("minder_search_errors", minder_search_errors, require_auth=True, description=TOOL_DESCRIPTIONS["minder_search_errors"])

    ResourceRegistry.register(transport.app, store)
    PromptRegistry.register(transport.app)
    return transport
