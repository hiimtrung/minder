from __future__ import annotations

import re
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.server import build_http_app
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _extract_client_key(html: str) -> str:
    match = re.search(r"(mkc_[A-Za-z0-9_\-]+)", html)
    if match is None:
        raise AssertionError("Expected client API key in HTML response")
    return match.group(1)


@pytest_asyncio.fixture
async def store() -> AsyncGenerator[RelationalStore, None]:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    return MinderConfig()


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
        login_response = await client.post("/dashboard/login", data={"api_key": admin_api_key})
        assert login_response.status_code == 303
        assert login_response.headers["location"] == "/dashboard"

        create_response = await client.post(
            "/dashboard/clients",
            data={
                "name": "Dashboard Gate Client",
                "slug": "dashboard-gate-client",
                "description": "Created from browser-only gate",
                "tool_scopes": "minder_query, minder_search_code",
                "repo_scopes": "/workspace/repo",
            },
        )
        assert create_response.status_code == 200
        assert "Client Created" in create_response.text
        first_client_key = _extract_client_key(create_response.text)

        dashboard_response = await client.get("/dashboard")
        assert dashboard_response.status_code == 200
        assert "Dashboard Gate Client" in dashboard_response.text
        assert "dashboard-gate-client" in dashboard_response.text

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
        assert "Onboarding Snippets" in detail_response.text
        assert "Recent Activity" in detail_response.text
        assert "codex" in detail_response.text

        connection_test_response = await client.post(
            f"/dashboard/clients/{client_id}/test-connection",
            data={"client_api_key": first_client_key},
        )
        assert connection_test_response.status_code == 200
        assert "Connection test passed" in connection_test_response.text
        assert "dashboard-gate-client" in connection_test_response.text

        rotate_response = await client.post(f"/dashboard/clients/{client_id}/rotate")
        assert rotate_response.status_code == 200
        assert "New Client API Key" in rotate_response.text
        rotated_key = _extract_client_key(rotate_response.text)
        assert rotated_key != first_client_key

        revoke_response = await client.post(f"/dashboard/clients/{client_id}/revoke")
        assert revoke_response.status_code == 303
        assert revoke_response.headers["location"] == f"/dashboard/clients/{client_id}"

        detail_after_revoke = await client.get(f"/dashboard/clients/{client_id}")
        assert detail_after_revoke.status_code == 200
        assert "All client keys are revoked" in detail_after_revoke.text
        assert "client.created" in detail_after_revoke.text
        assert "client.key_created" in detail_after_revoke.text
        assert "client.key_revoked" in detail_after_revoke.text

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
