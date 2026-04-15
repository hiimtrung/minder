from __future__ import annotations

import importlib.util
from pathlib import Path
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.auth.service import AuthError, AuthService
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.server import build_http_app
from minder.store.relational import RelationalStore
from minder.transport import SSETransport, StdioTransport

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _seed_dashboard_dist(dist: Path) -> None:
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>dashboard root</body></html>")
    (dist / "login" / "index.html").write_text("<html><body><h1>Admin Login</h1></body></html>")
    (dist / "setup" / "index.html").write_text("<html><body><h1>Create the first Minder admin</h1></body></html>")
    (dist / "clients" / "index.html").write_text(
        "<html><body><h1>Client Registry</h1><p>Manage MCP clients from the production dashboard.</p></body></html>"
    )


def _load_module(path: Path, module_name: str):  # noqa: ANN001, ANN201
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config(tmp_path: Path) -> MinderConfig:
    dist = tmp_path / "dashboard-dist"
    _seed_dashboard_dist(dist)
    config = MinderConfig(_env_file=None)
    config.dashboard.static_dir = str(dist)
    config.dashboard.base_path = "/dashboard"
    return config


@pytest.fixture
def cache() -> LRUCacheProvider:
    return LRUCacheProvider()


@pytest.fixture
def auth(store: RelationalStore, config: MinderConfig, cache: LRUCacheProvider) -> AuthService:
    return AuthService(store=store, config=config, cache=cache)


@pytest.mark.asyncio
async def test_phase4_1_gate(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        # 1. Fresh deployment serves Astro setup and login shells.
        login_page = await client.get("/dashboard/login")
        assert login_page.status_code == 303
        assert login_page.headers["location"] == "/dashboard/setup"

        setup_page = await client.get("/dashboard/setup")
        assert setup_page.status_code == 200
        assert "Create the first Minder admin" in setup_page.text

        # 2. Setup creates the first admin through the JSON contract.
        setup_submit = await client.post(
            "/v1/admin/setup",
            json={
                "username": "phase41_admin",
                "email": "phase41-admin@example.com",
                "display_name": "Phase 4.1 Admin",
            },
        )
        assert setup_submit.status_code == 201
        old_admin_key = setup_submit.json()["api_key"]
        assert old_admin_key.startswith("mk_")

        # 3. Browser login works with the bootstrap API key.
        browser_login = await client.post("/v1/admin/login", json={"api_key": old_admin_key})
        assert browser_login.status_code == 200

        dashboard = await client.get("/dashboard")
        assert dashboard.status_code == 303
        assert dashboard.headers["location"] == "/dashboard/repositories"

    # 4. Recovery script rotates the admin API key and invalidates the old one.
    recovery_module = _load_module(Path("scripts/reset_admin_api_key.py"), "phase41_reset_admin_api_key")
    recovery_result = await recovery_module.reset_admin_api_key(
        store,
        config,
        username="phase41_admin",
    )
    new_admin_key = recovery_result["api_key"]
    assert new_admin_key.startswith("mk_")
    assert new_admin_key != old_admin_key

    with pytest.raises(AuthError) as old_key_exc:
        await auth.authenticate_api_key(old_admin_key)
    assert old_key_exc.value.code == "AUTH_INVALID_KEY"

    admin_user = await auth.authenticate_api_key(new_admin_key)
    admin_token = auth.issue_jwt(admin_user)

    # 5. Admin creates a client; direct raw client key works over SSE.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        create_response = await client.post(
            "/v1/admin/clients",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Phase 4.1 Client",
                "slug": "phase41-client",
                "tool_scopes": ["inspect_principal"],
                "repo_scopes": ["/workspace/repo"],
            },
        )
    assert create_response.status_code == 201
    body = create_response.json()
    client_id = uuid.UUID(body["client"]["id"])
    client_api_key = body["client_api_key"]

    sse_transport = SSETransport(config=config, auth_service=auth, cache_provider=cache)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "scopes": principal.scopes,
        }

    sse_transport.register_tool("inspect_principal", inspect_principal, require_auth=True)
    sse_result = await sse_transport.call_tool("inspect_principal", client_key=client_api_key)
    assert sse_result["principal_type"] == "client"
    assert sse_result["scopes"] == ["inspect_principal"]

    # 6. Direct raw client key works over stdio bootstrap env.
    monkeypatch.setenv("MINDER_CLIENT_API_KEY", client_api_key)
    stdio_transport = StdioTransport(config=config, auth_service=auth, cache_provider=cache)
    stdio_transport.register_tool("inspect_principal", inspect_principal, require_auth=True)
    stdio_result = await stdio_transport.call_tool("inspect_principal")
    assert stdio_result["principal_type"] == "client"
    assert stdio_result["scopes"] == ["inspect_principal"]

    # 7. Revocation blocks further direct access for both SSE and stdio.
    await auth.revoke_client_api_keys(client_id=client_id, actor_user_id=admin_user.id)

    with pytest.raises(AuthError) as sse_exc:
        await sse_transport.call_tool("inspect_principal", client_key=client_api_key)
    assert sse_exc.value.code == "AUTH_INVALID_CLIENT_KEY"

    with pytest.raises(AuthError) as stdio_exc:
        await stdio_transport.call_tool("inspect_principal")
    assert stdio_exc.value.code == "AUTH_INVALID_CLIENT_KEY"
