from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.server import build_http_app
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _seed_dashboard_dist(dist: Path) -> None:
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>dashboard root</body></html>")
    (dist / "login" / "index.html").write_text("<html><body><h1>Admin Login</h1></body></html>")
    (dist / "setup" / "index.html").write_text("<html><body><h1>Create the first Minder admin</h1></body></html>")
    (dist / "clients" / "index.html").write_text(
        "<html><body><h1>Client Registry</h1><p>Manage MCP clients from the production dashboard.</p><p>Recent Activity</p><p>Copy-ready MCP snippets</p></body></html>"
    )


@pytest_asyncio.fixture
async def store() -> AsyncGenerator[RelationalStore, None]:
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
async def test_phase4_2_dashboard_gate(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    _admin_user, admin_api_key = await auth.register_user(
        email="phase42-admin@example.com",
        username="phase42_admin",
        display_name="Phase 4.2 Admin",
        role=UserRole.ADMIN,
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": admin_api_key})
        assert login_response.status_code == 200

        create_response = await client.post(
            "/v1/admin/clients",
            json={
                "name": "Dashboard Gate Client",
                "slug": "dashboard-gate-client",
                "description": "Created from browser-only gate",
                "tool_scopes": ["minder_query", "minder_search_code"],
                "repo_scopes": ["/workspace/repo"],
            },
        )
        assert create_response.status_code == 201
        first_client_key = create_response.json()["client_api_key"]

        dashboard_response = await client.get("/dashboard")
        assert dashboard_response.status_code == 303
        assert dashboard_response.headers["location"] == "/dashboard/clients"

        clients_api_response = await client.get("/v1/admin/clients")
        assert clients_api_response.status_code == 200
        created_client = next(
            client_info
            for client_info in clients_api_response.json()["clients"]
            if client_info["slug"] == "dashboard-gate-client"
        )
        client_id = created_client["id"]

        detail_response = await client.get(f"/dashboard/clients/{client_id}")
        assert detail_response.status_code == 200
        assert "Client Registry" in detail_response.text

        connection_test_response = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": first_client_key},
        )
        assert connection_test_response.status_code == 200
        assert connection_test_response.json()["client"]["slug"] == "dashboard-gate-client"

        rotate_response = await client.post(f"/v1/admin/clients/{client_id}/keys", json={})
        assert rotate_response.status_code == 201
        rotated_key = rotate_response.json()["client_api_key"]
        assert rotated_key != first_client_key

        revoke_response = await client.post(f"/v1/admin/clients/{client_id}/keys/revoke", json={})
        assert revoke_response.status_code == 200
        assert revoke_response.json()["revoked"] is True

        detail_after_revoke = await client.get(f"/dashboard/clients/{client_id}")
        assert detail_after_revoke.status_code == 200
        assert "Client Registry" in detail_after_revoke.text

        preflight_old_key = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": first_client_key},
        )
        preflight_rotated_key = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": rotated_key},
        )

    assert preflight_old_key.status_code == 401
    assert preflight_rotated_key.status_code == 401
