from __future__ import annotations

import asyncio
import html
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

from minder.auth.middleware import AuthMiddleware
from minder.auth.service import AuthService
from minder.cache.providers import LRUCacheProvider, RedisCacheProvider
from minder.config import MinderConfig, Settings
from minder.embedding.qwen import QwenEmbeddingProvider
from minder.graph.runtime import graph_runtime_name
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry
from minder.store.interfaces import ICacheProvider, IOperationalStore, IVectorStore
from minder.store.vector import VectorStore
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.query import QueryTools
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools
from minder.tools.memory import MemoryTools
from minder.transport import SSETransport, StdioTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import BaseRoute, Route

ADMIN_COOKIE_NAME = "minder_admin_token"


def build_store(config: MinderConfig) -> IOperationalStore:
    """Build the operational store based on config provider setting."""
    provider = config.relational_store.provider

    if provider == "mongodb":
        from minder.store.mongodb.client import MongoClient
        from minder.store.mongodb.operational_store import MongoOperationalStore

        client = MongoClient(
            uri=config.mongodb.uri,
            database=config.mongodb.database,
            min_pool_size=config.mongodb.min_pool_size,
            max_pool_size=config.mongodb.max_pool_size,
        )
        return MongoOperationalStore(client)  # type: ignore[return-value]

    # Default: SQLite via SQLAlchemy
    db_path = config.relational_store.db_path
    if db_path.startswith(("sqlite+", "postgresql+", "postgres://")):
        db_url = db_path
    else:
        expanded = Path(db_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{expanded}"
    return RelationalStore(db_url)  # type: ignore[return-value]


def build_cache(config: MinderConfig) -> ICacheProvider:
    """Build the cache provider based on config."""
    if config.cache.provider == "redis":
        return RedisCacheProvider(
            uri=config.redis.uri,
            prefix=config.redis.prefix,
            default_ttl=config.redis.cache_ttl,
        )
    return LRUCacheProvider(
        max_size=config.cache.max_size,
        default_ttl=config.cache.ttl_seconds,
    )


def build_vector_store(config: MinderConfig, store: IOperationalStore) -> IVectorStore:
    """Build the vector store based on config provider setting."""
    
    if config.vector_store.provider == "milvus":
        from minder.store.milvus.client import MilvusClient
        from minder.store.milvus.vector_store import MilvusVectorStore
        client = MilvusClient(uri=config.vector_store.uri)
        return MilvusVectorStore(client, prefix=config.vector_store.collection_prefix)
        
    return VectorStore(store, store)


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

    async def minder_auth_whoami(*, user=None) -> dict[str, Any]:  # noqa: ANN001
        token = auth_service.issue_jwt(user)
        return await auth_tools.minder_auth_whoami(token)

    async def minder_auth_manage(*, user=None, action: str) -> dict[str, object]:  # noqa: ANN001
        return await auth_tools.minder_auth_manage(actor_user_id=user.id, action=action)

    async def minder_auth_create_client(
        *,
        user,
        name: str,
        slug: str,
        description: str = "",
        tool_scopes: list[str] | None = None,
        repo_scopes: list[str] | None = None,
    ) -> dict[str, object]:  # noqa: ANN001
        return await auth_tools.minder_auth_create_client(
            actor_user_id=user.id,
            name=name,
            slug=slug,
            description=description,
            tool_scopes=tool_scopes,
            repo_scopes=repo_scopes,
        )

    async def minder_session_create(
        *, user, repo_id: str | None = None, project_context: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        return await session_tools.minder_session_create(
            user_id=user.id,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            project_context=project_context,
        )

    async def minder_session_save(
        *, user, session_id: str, state: dict[str, Any] | None = None, active_skills: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
        )

    async def minder_session_restore(*, user, session_id: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_restore(uuid.UUID(session_id))

    async def minder_session_context(
        *, user, session_id: str, branch: str, open_files: list[str]  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_context(
            uuid.UUID(session_id),
            branch=branch,
            open_files=open_files,
        )

    async def minder_workflow_get(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_get(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_step(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_step(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_update(
        *,
        user,
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

    async def minder_workflow_guard(*, user, repo_id: str, requested_step: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=uuid.UUID(repo_id),
            requested_step=requested_step,
        )

    async def minder_memory_store(
        *, user, title: str, content: str, tags: list[str], language: str  # noqa: ANN001
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
        description="Verify authentication round-trip.",
    )

    transport.register_tool("minder_auth_login", minder_auth_login, require_auth=False)
    transport.register_tool(
        "minder_auth_exchange_client_key",
        minder_auth_exchange_client_key,
        require_auth=False,
    )
    transport.register_tool("minder_auth_whoami", minder_auth_whoami, require_auth=True)
    transport.register_tool("minder_auth_manage", minder_auth_manage, require_auth=True)
    transport.register_tool("minder_auth_create_client", minder_auth_create_client, require_auth=True)
    transport.register_tool("minder_session_create", minder_session_create, require_auth=True)
    transport.register_tool("minder_session_save", minder_session_save, require_auth=True)
    transport.register_tool("minder_session_restore", minder_session_restore, require_auth=True)
    transport.register_tool("minder_session_context", minder_session_context, require_auth=True)
    transport.register_tool("minder_workflow_get", minder_workflow_get, require_auth=True)
    transport.register_tool("minder_workflow_step", minder_workflow_step, require_auth=True)
    transport.register_tool("minder_workflow_update", minder_workflow_update, require_auth=True)
    transport.register_tool("minder_workflow_guard", minder_workflow_guard, require_auth=True)
    transport.register_tool("minder_memory_store", minder_memory_store, require_auth=True)
    transport.register_tool("minder_memory_recall", minder_memory_recall, require_auth=True)
    transport.register_tool("minder_memory_list", minder_memory_list, require_auth=True)
    transport.register_tool("minder_memory_delete", minder_memory_delete, require_auth=True)
    transport.register_tool("minder_search", minder_search, require_auth=True)
    transport.register_tool("minder_query", minder_query, require_auth=True)
    transport.register_tool("minder_search_code", minder_search_code, require_auth=True)
    transport.register_tool("minder_search_errors", minder_search_errors, require_auth=True)

    # ------------------------------------------------------------------
    # P3-T11: Register MCP resources and prompts
    # ------------------------------------------------------------------
    ResourceRegistry.register(transport.app, store)
    PromptRegistry.register(transport.app)

    return transport


def build_http_routes(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    cache: ICacheProvider | None = None,
) -> list[BaseRoute]:
    auth_service = AuthService(store, config, cache=cache)
    middleware = AuthMiddleware(auth_service)
    auth_tools = AuthTools(store, auth_service)

    def _serialize_client(client: Any) -> dict[str, Any]:
        return {
            "id": str(client.id),
            "name": client.name,
            "slug": client.slug,
            "description": getattr(client, "description", ""),
            "status": client.status,
            "tool_scopes": list(client.tool_scopes),
            "repo_scopes": list(client.repo_scopes),
            "workflow_scopes": list(getattr(client, "workflow_scopes", [])),
            "transport_modes": list(getattr(client, "transport_modes", [])),
        }

    def _onboarding_templates(client: Any) -> dict[str, str]:
        exchange_url = "/v1/auth/token-exchange"
        query_hint = client.tool_scopes[0] if client.tool_scopes else "minder_query"
        base_url = f"http://localhost:{config.server.port}"
        return {
            "codex": (
                f'{{"server_url":"{base_url}/sse","client_api_key":"<mkc_...>",'
                f'"bootstrap_path":"{exchange_url}","client_slug":"{client.slug}","preferred_tool":"{query_hint}"}}'
            ),
            "copilot": (
                f'{{"type":"mcp","url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}},"client":"{client.slug}"}}'
            ),
            "claude_desktop": (
                f'{{"mcpServers":{{"minder":{{"url":"{base_url}/sse","headers":{{"X-Minder-Client-Key":"<mkc_...>"}},"client":"{client.slug}"}}}}}}'
            ),
        }

    def _request_token(request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        if authorization:
            return authorization
        cookie_token = request.cookies.get(ADMIN_COOKIE_NAME)
        if cookie_token:
            return f"Bearer {cookie_token}"
        return None

    async def _admin_user_from_request(request: Request) -> Any:
        authorization = _request_token(request)
        user = await middleware.authenticate(authorization)
        if user.role != "admin":
            raise PermissionError("Admin role required")
        return user

    def _dashboard_login_html(error_message: str | None = None) -> str:
        escaped_error = html.escape(error_message) if error_message else ""
        error_block = (
            f"<p class='error' role='alert'>{escaped_error}</p>" if escaped_error else ""
        )
        return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Minder Admin Sign In</title>
    <style>
      :root {{
        --bg: #f5efe6;
        --panel: #fffaf2;
        --ink: #1f1b18;
        --accent: #aa3c29;
        --muted: #6f675f;
        --border: #decfbb;
        --danger: #8d1d1d;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
        font-family: "Iowan Old Style", "Palatino Linotype", serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(170, 60, 41, 0.18), transparent 28%),
          linear-gradient(135deg, #f8f1e6, var(--bg));
      }}
      .card {{
        width: min(480px, 100%);
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 32px;
        box-shadow: 0 18px 60px rgba(35, 24, 18, 0.12);
      }}
      h1 {{
        margin: 0 0 8px;
        font-size: 2rem;
      }}
      p {{
        margin: 0 0 16px;
        color: var(--muted);
      }}
      label {{
        display: block;
        margin-bottom: 8px;
        font-size: 0.95rem;
      }}
      input {{
        width: 100%;
        box-sizing: border-box;
        margin-bottom: 16px;
        padding: 14px 16px;
        border: 1px solid var(--border);
        border-radius: 14px;
        font: inherit;
        background: white;
      }}
      button {{
        width: 100%;
        border: 0;
        border-radius: 999px;
        padding: 14px 18px;
        font: inherit;
        color: white;
        background: var(--accent);
        cursor: pointer;
      }}
      .error {{
        color: var(--danger);
        margin-bottom: 16px;
      }}
      .hint {{
        margin-top: 20px;
        font-size: 0.95rem;
      }}
      code {{
        font-family: "SFMono-Regular", Consolas, monospace;
        background: rgba(170, 60, 41, 0.08);
        padding: 2px 6px;
        border-radius: 6px;
      }}
    </style>
  </head>
  <body>
    <main class="card">
      <h1>Admin Sign In</h1>
      <p>Use the admin API key created during bootstrap to open the Minder dashboard in a browser.</p>
      {error_block}
      <form method="post" action="/dashboard/login">
        <label for="api_key">Admin API Key</label>
        <input id="api_key" name="api_key" type="password" autocomplete="current-password" required />
        <button type="submit">Open Dashboard</button>
      </form>
      <p class="hint">Need a first admin key? Run <code>scripts/create_admin.py</code> inside the Minder container.</p>
    </main>
  </body>
</html>
"""

    def _setup_html(error_message: str | None = None) -> str:
        error_block = f'<div class="error">{html.escape(error_message)}</div>' if error_message else ""
        return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Minder Setup</title>
    <style>
      :root {{ --bg: #f4efe6; --panel: #fffaf0; --ink: #1d1b18; --border: #d7c8b4; --danger: #aa3c29; }}
      body {{ font-family: "Iowan Old Style", serif; background: var(--bg); color: var(--ink); margin:0; padding: 40px; display: grid; place-items: center; min-height: 100vh; }}
      .card {{ background: var(--panel); border: 1px solid var(--border); padding: 40px; border-radius: 12px; max-width: 400px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }}
      h1 {{ margin-top: 0; }}
      form {{ display: flex; flex-direction: column; gap: 16px; margin-top: 20px; }}
      label {{ font-weight: bold; font-size: 0.9rem; }}
      input {{ padding: 10px; border: 1px solid var(--border); border-radius: 4px; font-family: inherit; }}
      button {{ padding: 12px; background: var(--ink); color: #fff; border: none; border-radius: 6px; cursor: pointer; border: 1px solid transparent; font-family: inherit; font-size: 1rem; margin-top: 10px; }}
      .error {{ color: var(--danger); margin-bottom: 16px; }}
    </style>
  </head>
  <body>
    <main class="card">
      <h1>Initial Admin Setup</h1>
      <p>Welcome to Minder! Let's create your first admin user.</p>
      {error_block}
      <form method="post" action="/setup">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" required />
        <label for="email">Email</label>
        <input id="email" name="email" type="email" required />
        <label for="display_name">Display Name</label>
        <input id="display_name" name="display_name" type="text" required />
        <button type="submit">Create Admin Account</button>
      </form>
    </main>
  </body>
</html>
"""

    def _setup_complete_html(api_key: str) -> str:
        escaped_key = html.escape(api_key)
        return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Minder Setup Complete</title>
    <style>
      :root {{ --bg: #f4efe6; --panel: #fffaf0; --ink: #1d1b18; --border: #d7c8b4; --accent: #af3b2a; }}
      body {{ font-family: "Iowan Old Style", serif; background: var(--bg); color: var(--ink); margin:0; padding: 40px; display: grid; place-items: center; min-height: 100vh; }}
      .card {{ background: var(--panel); border: 1px solid var(--border); padding: 40px; border-radius: 12px; max-width: 560px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }}
      h1 {{ margin-top: 0; }}
      code {{ display: block; margin: 18px 0; padding: 14px 16px; border-radius: 8px; background: #fff; border: 1px solid var(--border); word-break: break-all; font-family: "SFMono-Regular", Consolas, monospace; }}
      a {{ color: white; background: var(--accent); text-decoration: none; padding: 12px 16px; border-radius: 999px; display: inline-block; }}
      p {{ line-height: 1.5; }}
    </style>
  </head>
  <body>
    <main class="card">
      <h1>Setup Complete</h1>
      <p>Copy this API key now. Minder will not show it again after you leave this page.</p>
      <code>{escaped_key}</code>
      <a href="/dashboard/login">Continue to Admin Sign In</a>
    </main>
  </body>
</html>
"""

    async def setup_page(request: Request) -> HTMLResponse | RedirectResponse:
        if await auth_service.has_admin_users():
            return HTMLResponse("Admin already set up", status_code=403)
        return HTMLResponse(_setup_html(), status_code=200)

    async def setup_submit(request: Request) -> HTMLResponse | RedirectResponse:
        if await auth_service.has_admin_users():
            return HTMLResponse("Admin already set up", status_code=403)
        
        form = await request.form()
        username = str(form.get("username", "")).strip()
        email = str(form.get("email", "")).strip()
        display_name = str(form.get("display_name", "")).strip()
        
        if not all([username, email, display_name]):
            return HTMLResponse(_setup_html("All fields are required."), status_code=400)
            
        try:
            _user, api_key = await auth_service.register_user(
                email=email,
                username=username,
                display_name=display_name,
                role="admin",
            )
            return RedirectResponse(f"/dashboard-setup-complete?api_key={api_key}", status_code=303)
        except Exception as exc:
            return HTMLResponse(_setup_html(str(exc)), status_code=400)

    async def setup_complete(request: Request) -> HTMLResponse | RedirectResponse:
        if not await auth_service.has_admin_users():
            return RedirectResponse(url="/setup", status_code=303)
        api_key = str(request.query_params.get("api_key", "")).strip()
        if not api_key:
            return RedirectResponse(url="/dashboard/login", status_code=303)
        return HTMLResponse(_setup_complete_html(api_key), status_code=200)

    async def dashboard_login_page(request: Request) -> HTMLResponse | RedirectResponse:
        if not await auth_service.has_admin_users():
            return RedirectResponse(url="/setup", status_code=303)
        try:
            await _admin_user_from_request(request)
        except Exception:
            return HTMLResponse(_dashboard_login_html(), status_code=200)
        return RedirectResponse(url="/dashboard", status_code=303)

    async def dashboard_login(request: Request) -> HTMLResponse | RedirectResponse:
        form = await request.form()
        api_key = str(form.get("api_key", "")).strip()
        if not api_key:
            return HTMLResponse(_dashboard_login_html("Admin API key is required."), status_code=400)
        try:
            user = await auth_service.authenticate_api_key(api_key)
        except Exception:
            return HTMLResponse(_dashboard_login_html("Invalid admin API key."), status_code=401)
        if user.role != "admin":
            return HTMLResponse(_dashboard_login_html("Admin role required."), status_code=403)
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            auth_service.issue_jwt(user),
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
            max_age=config.auth.jwt_expiry_hours * 3600,
        )
        return response

    async def dashboard_logout(request: Request) -> RedirectResponse:
        del request
        response = RedirectResponse(url="/dashboard/login", status_code=303)
        response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
        return response

    async def token_exchange(request: Request) -> JSONResponse:
        payload = await request.json()
        client_api_key = payload["client_api_key"]
        requested_scopes = payload.get("requested_scopes")
        exchange = await auth_tools.minder_auth_exchange_client_key(
            client_api_key,
            requested_scopes=requested_scopes,
        )
        return JSONResponse(exchange)

    async def gateway_test_connection(request: Request) -> JSONResponse:
        payload = await request.json()
        client_api_key = payload["client_api_key"]
        try:
            client = await auth_service.authenticate_client_api_key(client_api_key)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        return JSONResponse(
            {
                "ok": True,
                "client": _serialize_client(client),
                "templates": _onboarding_templates(client),
            }
        )

    async def list_clients(request: Request) -> JSONResponse:
        try:
            await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        clients = await store.list_clients()
        return JSONResponse(
            {
                "clients": [
                    _serialize_client(client)
                    for client in clients
                ]
            }
        )

    async def create_client(request: Request) -> JSONResponse:
        try:
            user = await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        payload = await request.json()
        created = await auth_tools.minder_auth_create_client(
            actor_user_id=user.id,
            name=payload["name"],
            slug=payload["slug"],
            description=payload.get("description", ""),
            tool_scopes=payload.get("tool_scopes"),
            repo_scopes=payload.get("repo_scopes"),
        )
        return JSONResponse(created, status_code=201)

    async def admin_clients(request: Request) -> JSONResponse:
        if request.method == "GET":
            return await list_clients(request)
        return await create_client(request)

    async def client_detail(request: Request) -> JSONResponse:
        try:
            user = await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        del user

        client_id = request.path_params["client_id"]
        client = await store.get_client_by_id(client_id)
        if client is None:
            return JSONResponse({"error": "Client not found"}, status_code=404)

        if request.method == "GET":
            return JSONResponse({"client": _serialize_client(client)})

        payload = await request.json()
        updated = await store.update_client(
            client_id,
            description=payload.get("description", getattr(client, "description", "")),
            repo_scopes=payload.get("repo_scopes", list(client.repo_scopes)),
            tool_scopes=payload.get("tool_scopes", list(client.tool_scopes)),
        )
        if updated is None:
            return JSONResponse({"error": "Client not found"}, status_code=404)
        return JSONResponse({"client": _serialize_client(updated)})

    async def client_key_rotate(request: Request) -> JSONResponse:
        try:
            user = await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = request.path_params["client_id"]
        try:
            client_api_key = await auth_service.create_client_api_key(
                client_id=client_id,
                created_by_user_id=user.id,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse({"client_api_key": client_api_key}, status_code=201)

    async def client_key_revoke(request: Request) -> JSONResponse:
        try:
            user = await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = request.path_params["client_id"]
        await auth_service.revoke_client_api_keys(client_id, actor_user_id=user.id)
        return JSONResponse({"revoked": True})

    async def client_onboarding(request: Request) -> JSONResponse:
        try:
            await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        client_id = request.path_params["client_id"]
        client = await store.get_client_by_id(client_id)
        if client is None:
            return JSONResponse({"error": "Client not found"}, status_code=404)
        return JSONResponse(
            {
                "client": _serialize_client(client),
                "templates": _onboarding_templates(client),
            }
        )

    async def dashboard(request: Request) -> HTMLResponse | RedirectResponse:
        if not await auth_service.has_admin_users():
            return RedirectResponse(url="/setup", status_code=303)
        try:
            await _admin_user_from_request(request)
        except PermissionError:
            return HTMLResponse("Admin role required", status_code=403)
        except Exception:
            return RedirectResponse(url="/dashboard/login", status_code=303)

        clients = await store.list_clients()
        cards = "\n".join(
            (
                f"<article class='client-card'>"
                f"<h2>{html.escape(client.name)}</h2>"
                f"<p class='slug'>{html.escape(client.slug)}</p>"
                f"<p>{html.escape(getattr(client, 'description', '') or 'No description yet.')}</p>"
                f"<p class='scopes'>{html.escape(', '.join(client.tool_scopes) or 'No scopes assigned')}</p>"
                f"</article>"
            )
            for client in clients
        )
        page_html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Minder Dashboard</title>
    <style>
      :root {{
        --bg: #f4efe6;
        --panel: #fffaf0;
        --ink: #1d1b18;
        --accent: #af3b2a;
        --muted: #6f675f;
        --border: #d7c8b4;
      }}
      body {{
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", serif;
        background:
          radial-gradient(circle at top left, rgba(175, 59, 42, 0.18), transparent 32%),
          linear-gradient(135deg, #f7f0e5, var(--bg));
        color: var(--ink);
      }}
      main {{
        max-width: 1080px;
        margin: 0 auto;
        padding: 48px 20px 72px;
      }}
      .actions {{
        display: flex;
        justify-content: flex-end;
        margin-bottom: 24px;
      }}
      .logout {{
        border: 1px solid var(--border);
        background: white;
        color: var(--ink);
        border-radius: 999px;
        padding: 10px 16px;
        font: inherit;
        cursor: pointer;
      }}
      .hero {{
        display: grid;
        gap: 12px;
        margin-bottom: 28px;
      }}
      .hero h1 {{
        margin: 0;
        font-size: clamp(2.2rem, 5vw, 4.2rem);
        line-height: 0.95;
      }}
      .hero p {{
        max-width: 60ch;
        margin: 0;
        color: var(--muted);
        font-size: 1.05rem;
      }}
      .board {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }}
      .client-card {{
        border: 1px solid var(--border);
        background: var(--panel);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 10px 30px rgba(29, 27, 24, 0.06);
      }}
      .client-card h2 {{
        margin: 0 0 6px;
        font-size: 1.2rem;
      }}
      .slug {{
        margin: 0 0 10px;
        color: var(--accent);
      }}
      .scopes {{
        margin: 12px 0 0;
        color: var(--muted);
        font-size: 0.95rem;
      }}
      .label {{
        display: inline-block;
        margin-bottom: 6px;
        font-size: 0.8rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--accent);
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="actions">
        <form method="post" action="/dashboard/logout">
          <button class="logout" type="submit">Sign Out</button>
        </form>
      </div>
      <section class="hero">
        <span class="label">Client Registry</span>
        <h1>Minder Gateway Dashboard</h1>
        <p>Manage MCP clients, bootstrap credentials, and onboarding templates for Codex, Copilot-style clients, and Claude Desktop from one place.</p>
      </section>
      <section class="board">
        {cards or "<article class='client-card'><h2>No clients yet</h2><p>Create a client from the admin API to generate onboarding templates.</p></article>"}
      </section>
    </main>
  </body>
</html>
"""
        return HTMLResponse(page_html)

    async def admin_audit(request: Request) -> JSONResponse:
        try:
            await _admin_user_from_request(request)
        except PermissionError:
            return JSONResponse({"error": "Admin role required"}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        actor_id = request.query_params.get("actor_id")
        events = await store.list_audit_logs(actor_id=actor_id)
        return JSONResponse(
            {
                "events": [
                    {
                        "id": str(event.id),
                        "actor_type": event.actor_type,
                        "actor_id": event.actor_id,
                        "event_type": event.event_type,
                        "resource_type": event.resource_type,
                        "resource_id": event.resource_id,
                        "outcome": event.outcome,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in events
                ]
            }
        )

    return [
        Route("/setup", setup_page, methods=["GET"]),
        Route("/setup", setup_submit, methods=["POST"]),
        Route("/dashboard-setup-complete", setup_complete, methods=["GET"]),
        Route("/v1/auth/token-exchange", token_exchange, methods=["POST"]),
        Route("/v1/gateway/test-connection", gateway_test_connection, methods=["POST"]),
        Route("/dashboard/login", dashboard_login_page, methods=["GET"]),
        Route("/dashboard/login", dashboard_login, methods=["POST"]),
        Route("/dashboard/logout", dashboard_logout, methods=["POST"]),
        Route("/v1/admin/clients", admin_clients, methods=["GET", "POST"]),
        Route("/v1/admin/clients/{client_id:uuid}", client_detail, methods=["GET", "PATCH"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys", client_key_rotate, methods=["POST"]),
        Route("/v1/admin/clients/{client_id:uuid}/keys/revoke", client_key_revoke, methods=["POST"]),
        Route("/v1/admin/onboarding/{client_id:uuid}", client_onboarding, methods=["GET"]),
        Route("/v1/admin/audit", admin_audit, methods=["GET"]),
        Route("/dashboard", dashboard, methods=["GET"]),
    ]


def build_http_app(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    cache: ICacheProvider | None = None,
) -> Starlette:
    return Starlette(routes=build_http_routes(config=config, store=store, cache=cache))


def runtime_summary(config: MinderConfig) -> dict[str, object]:
    llm = QwenLocalLLM(config.llm.model_path, runtime="auto")
    embedder = QwenEmbeddingProvider(
        config.embedding.model_path,
        dimensions=config.embedding.dimensions,
        runtime="auto",
    )
    fallback = OpenAIFallbackLLM(config.llm.openai_api_key, config.llm.openai_model, runtime="auto")
    return {
        "transport": config.server.transport,
        "host": config.server.host,
        "port": config.server.port,
        "orchestration_runtime_requested": config.workflow.orchestration_runtime,
        "orchestration_runtime_effective": graph_runtime_name(config.workflow.orchestration_runtime),
        "llm_model_path": str(Path(config.llm.model_path).expanduser()),
        "llm_runtime_effective": llm.runtime,
        "embedding_model_path": str(Path(config.embedding.model_path).expanduser()),
        "embedding_runtime_effective": embedder.runtime,
        "openai_fallback_configured": fallback.available(),
        "openai_fallback_runtime_effective": fallback.runtime,
    }


async def _async_run() -> None:
    """Single-loop async entrypoint.

    All async operations (store init, vector setup, admin check, transport
    lifecycle, teardown) run inside ONE event loop.  This is required when
    using Motor (MongoDB async driver): AsyncIOMotorClient binds to the loop
    that is current at first use.  Multiple asyncio.run() calls each create
    and immediately close a fresh loop, causing Motor's run_in_executor to
    schedule work on an already-closed loop → RuntimeError.
    """
    print("MINDER SERVER STARTING", file=sys.stderr, flush=True)
    config = Settings()
    log_level = getattr(logging, config.server.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, stream=sys.stderr)
    store = build_store(config)
    print(f"MINDER DB URL: {config.relational_store.db_path}", file=sys.stderr, flush=True)
    await store.init_db()
    vector_store = build_vector_store(config, store)
    if hasattr(vector_store, "setup"):
        await vector_store.setup()
    cache = build_cache(config)

    admin = await store.get_user_by_username("admin")
    print(f"MINDER ADMIN EXISTS: {admin is not None}", file=sys.stderr, flush=True)

    transport = build_transport(config=config, store=store, vector_store=vector_store, cache=cache)
    store_type = config.relational_store.provider
    cache_type = config.cache.provider
    print(
        f"Minder store={store_type} cache={cache_type} transport={transport.transport_name} host={config.server.host}:{config.server.port}",
        file=sys.stderr,
        flush=True,
    )
    print("Minder runtime summary:", runtime_summary(config), file=sys.stderr, flush=True)
    try:
        if transport.transport_name == "stdio":
            await transport.app.run_stdio_async()
        else:
            print(f"Starting SSE on {config.server.host}:{config.server.port}", file=sys.stderr, flush=True)
            if hasattr(transport, "run"):
                await transport.run()
            else:
                await transport.app.run_sse_async()
    finally:
        await store.dispose()
        await cache.close()


def _run() -> None:
    """Synchronous entrypoint — delegates everything to _async_run()."""
    asyncio.run(_async_run())


def main() -> None:
    _run()


if __name__ == "__main__":
    main()
