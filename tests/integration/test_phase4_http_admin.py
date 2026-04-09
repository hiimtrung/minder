from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider, RedisCacheProvider
from minder.config import MinderConfig
from minder.server import build_http_app
from minder.store.relational import RelationalStore

try:
    import fakeredis.aioredis

    _fakeredis_available = True
except ImportError:
    _fakeredis_available = False


IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"
requires_fakeredis = pytest.mark.skipif(
    not _fakeredis_available,
    reason="fakeredis not installed",
)


def _seed_dashboard_dist(dist: Path) -> None:
    (dist / "clients").mkdir(parents=True)
    (dist / "login").mkdir(parents=True)
    (dist / "setup").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>dashboard root</body></html>")
    (dist / "login" / "index.html").write_text(
        "<html><body><h1>Admin Login</h1><p>Sign in with your admin API key</p></body></html>"
    )
    (dist / "setup" / "index.html").write_text(
        "<html><body><h1>Create the first Minder admin</h1></body></html>"
    )
    (dist / "clients" / "index.html").write_text(
        "<html><body><h1>Client Registry</h1><p>Manage MCP clients from the production dashboard.</p><p>Create client</p><p>Recent Activity</p><p>Copy-ready MCP snippets</p></body></html>"
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
    config = MinderConfig()
    config.dashboard.static_dir = str(dist)
    config.dashboard.base_path = "/dashboard"
    config.dashboard.legacy_compat_enabled = False
    return config


@pytest.fixture
def cache() -> LRUCacheProvider:
    return LRUCacheProvider()


@pytest.fixture
def auth(store: RelationalStore, config: MinderConfig, cache: LRUCacheProvider) -> AuthService:
    return AuthService(store=store, config=config, cache=cache)


@pytest_asyncio.fixture
async def admin_token(auth: AuthService) -> str:
    admin, _ = await auth.register_user(
        email="http-admin@example.com",
        username="http_admin",
        display_name="HTTP Admin",
        role=UserRole.ADMIN,
    )
    return auth.issue_jwt(admin)


@pytest.mark.asyncio
async def test_token_exchange_endpoint_returns_access_token(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin, _ = await auth.register_user(
        email="exchange-admin@example.com",
        username="exchange_admin",
        display_name="Exchange Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Codex Local",
        slug="codex-local-http",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query", "minder_search_code"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/token-exchange",
            json={
                "client_api_key": client_api_key,
                "requested_scopes": ["minder_query"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["client_id"]
    assert body["access_token"]


@pytest.mark.asyncio
async def test_admin_can_create_and_list_clients_via_http(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    admin_token: str,
) -> None:
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        create_response = await client.post(
            "/v1/admin/clients",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "VS Code Copilot",
                "slug": "copilot-http",
                "tool_scopes": ["minder_query"],
                "repo_scopes": ["/workspace/repo"],
            },
        )
        list_response = await client.get(
            "/v1/admin/clients",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["client"]["slug"] == "copilot-http"
    assert created["client_api_key"].startswith("mkc_")

    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["clients"]
    assert listed["clients"][0]["slug"] == "copilot-http"


@pytest.mark.asyncio
async def test_admin_can_query_audit_log_via_http(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    admin_token: str,
) -> None:
    admin = await auth.get_user_from_jwt(admin_token)
    await auth.register_client(
        name="Claude Desktop",
        slug="claude-http",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["events"]
    assert any(event["event_type"] == "client.created" for event in body["events"])


@requires_fakeredis
@pytest.mark.asyncio
async def test_token_exchange_persists_client_session_in_redis_cache(
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    cache = RedisCacheProvider.__new__(RedisCacheProvider)
    cache._prefix = "phase4:"
    cache._default_ttl = 3600
    cache._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    auth = AuthService(store=store, config=config, cache=cache)

    admin, _ = await auth.register_user(
        email="redis-admin@example.com",
        username="redis_admin",
        display_name="Redis Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Codex Redis",
        slug="codex-redis",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/auth/token-exchange",
            json={"client_api_key": client_api_key},
        )

    assert response.status_code == 200
    payload = auth.validate_jwt(response.json()["access_token"])
    cache_key = f"client_session:{payload['jti']}"
    assert await cache.exists(cache_key) is True
    principal = await auth.get_principal_from_token(response.json()["access_token"])
    assert principal.principal_type == "client"

    await cache.close()


@pytest.mark.asyncio
async def test_admin_can_view_and_update_client_detail_via_http(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    admin_token: str,
) -> None:
    admin = await auth.get_user_from_jwt(admin_token)
    created_client, _ = await auth.register_client(
        name="Dashboard Client",
        slug="dashboard-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
        repo_scopes=["/workspace/old"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        detail_response = await client.get(
            f"/v1/admin/clients/{created_client.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        update_response = await client.patch(
            f"/v1/admin/clients/{created_client.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "description": "Updated dashboard-managed client",
                "repo_scopes": ["/workspace/new"],
                "tool_scopes": ["minder_query", "minder_search_code"],
            },
        )

    assert detail_response.status_code == 200
    assert detail_response.json()["client"]["slug"] == "dashboard-client"

    assert update_response.status_code == 200
    updated = update_response.json()["client"]
    assert updated["description"] == "Updated dashboard-managed client"
    assert updated["repo_scopes"] == ["/workspace/new"]
    assert updated["tool_scopes"] == ["minder_query", "minder_search_code"]


@pytest.mark.asyncio
async def test_admin_can_rotate_and_revoke_client_keys_via_http(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    admin_token: str,
) -> None:
    admin = await auth.get_user_from_jwt(admin_token)
    created_client, client_api_key = await auth.register_client(
        name="Rotate Client",
        slug="rotate-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        rotate_response = await client.post(
            f"/v1/admin/clients/{created_client.id}/keys",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        revoke_response = await client.post(
            f"/v1/admin/clients/{created_client.id}/keys/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        connection_test_after_revoke = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": client_api_key},
        )

    assert rotate_response.status_code == 201
    rotated = rotate_response.json()
    assert rotated["client_api_key"].startswith("mkc_")
    assert rotated["client_api_key"] != client_api_key

    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked"] is True

    assert connection_test_after_revoke.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_and_onboarding_routes_render_client_setup(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
    admin_token: str,
) -> None:
    admin = await auth.get_user_from_jwt(admin_token)
    created_client, _ = await auth.register_client(
        name="Onboarding Client",
        slug="onboarding-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query", "minder_search_code"],
        repo_scopes=["/workspace/repo"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        dashboard_response = await client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        onboarding_response = await client.get(
            f"/v1/admin/onboarding/{created_client.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert dashboard_response.status_code == 303
    assert dashboard_response.headers["location"] == "/dashboard/clients"

    assert onboarding_response.status_code == 200
    onboarding = onboarding_response.json()
    assert "codex" in onboarding["templates"]
    assert "copilot" in onboarding["templates"]
    assert "claude_desktop" in onboarding["templates"]
    assert "onboarding-client" in onboarding["templates"]["codex"]


@pytest.mark.asyncio
async def test_dashboard_login_page_renders_without_auth(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    # Must have at least one admin to avoid /setup redirect
    await auth.register_user(email="admin@test.com", username="admin", display_name="Admin", role=UserRole.ADMIN)
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/dashboard/login")

    assert response.status_code == 200
    assert "Admin Login" in response.text
    assert "Sign in with your admin API key" in response.text


@pytest.mark.asyncio
async def test_dashboard_login_sets_cookie_and_redirects_to_dashboard(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    _, api_key = await auth.register_user(
        email="browser-admin@example.com",
        username="browser_admin",
        display_name="Browser Admin",
        role=UserRole.ADMIN,
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})

    assert login_response.status_code == 200
    assert login_response.json()["ok"] is True
    cookie_header = login_response.headers.get("set-cookie", "")
    assert "minder_admin_token=" in cookie_header
    assert "HttpOnly" in cookie_header


@pytest.mark.asyncio
async def test_json_admin_setup_login_logout_and_session_endpoints(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
) -> None:
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        setup_response = await client.post(
            "/v1/admin/setup",
            json={
                "username": "json_admin",
                "email": "json-admin@example.com",
                "display_name": "JSON Admin",
            },
        )
        assert setup_response.status_code == 201
        api_key = setup_response.json()["api_key"]
        assert api_key.startswith("mk_")

        login_response = await client.post(
            "/v1/admin/login",
            json={"api_key": api_key},
        )
        assert login_response.status_code == 200
        assert login_response.json()["ok"] is True
        assert "minder_admin_token=" in login_response.headers.get("set-cookie", "")

        session_response = await client.get("/v1/admin/session")
        assert session_response.status_code == 200
        assert session_response.json()["admin"]["username"] == "json_admin"

        logout_response = await client.post("/v1/admin/logout", json={})
        assert logout_response.status_code == 200
        assert logout_response.json()["ok"] is True

        session_after_logout = await client.get("/v1/admin/session")
        assert session_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_supports_cookie_login_and_logout(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin_user, api_key = await auth.register_user(
        email="cookie-admin@example.com",
        username="cookie_admin",
        display_name="Cookie Admin",
        role=UserRole.ADMIN,
    )
    await auth.register_client(
        name="Cookie Dashboard Client",
        slug="cookie-dashboard-client",
        created_by_user_id=admin_user.id,
        tool_scopes=["minder_query"],
        repo_scopes=["/workspace/repo"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        assert login_response.status_code == 200

        dashboard_response = await client.get("/dashboard")
        assert dashboard_response.status_code == 303
        assert dashboard_response.headers["location"] == "/dashboard/clients"

        logout_response = await client.post("/v1/admin/logout", json={})
        assert logout_response.status_code == 200
        cleared_cookie = logout_response.headers.get("set-cookie", "")
        assert "minder_admin_token=" in cleared_cookie

        dashboard_after_logout = await client.get("/dashboard", follow_redirects=False)
        assert dashboard_after_logout.status_code == 303
        assert dashboard_after_logout.headers["location"] == "/dashboard/login"


@pytest.mark.asyncio
async def test_dashboard_renders_client_registry_and_create_form(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin_user, api_key = await auth.register_user(
        email="registry-admin@example.com",
        username="registry_admin",
        display_name="Registry Admin",
        role=UserRole.ADMIN,
    )
    await auth.register_client(
        name="Registry Client",
        slug="registry-client",
        created_by_user_id=admin_user.id,
        tool_scopes=["minder_query"],
        repo_scopes=["/workspace/repo"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        assert login_response.status_code == 200
        dashboard_response = await client.get("/dashboard")

    assert dashboard_response.status_code == 303
    assert dashboard_response.headers["location"] == "/dashboard/clients"


@pytest.mark.asyncio
async def test_dashboard_can_create_client_from_browser_session(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    _admin_user, api_key = await auth.register_user(
        email="browser-create-admin@example.com",
        username="browser_create_admin",
        display_name="Browser Create Admin",
        role=UserRole.ADMIN,
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        assert login_response.status_code == 200

        create_response = await client.post(
            "/v1/admin/clients",
            json={
                "name": "Browser Created Client",
                "slug": "browser-created-client",
                "description": "Created from the dashboard form",
                "tool_scopes": ["minder_query", "minder_search_code"],
                "repo_scopes": ["*", "/workspace/docs"],
            },
        )
        dashboard_response = await client.get("/dashboard")

    assert create_response.status_code == 201
    assert create_response.json()["client"]["name"] == "Browser Created Client"
    assert create_response.json()["client_api_key"].startswith("mkc_")

    assert dashboard_response.status_code == 303
    assert dashboard_response.headers["location"] == "/dashboard/clients"


@pytest.mark.asyncio
async def test_dashboard_client_detail_supports_onboarding_rotate_and_revoke(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin_user, api_key = await auth.register_user(
        email="detail-admin@example.com",
        username="detail_admin",
        display_name="Detail Admin",
        role=UserRole.ADMIN,
    )
    created_client, original_client_key = await auth.register_client(
        name="Detail Client",
        slug="detail-client",
        created_by_user_id=admin_user.id,
        tool_scopes=["minder_query", "minder_search_code"],
        repo_scopes=["/workspace/repo"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        assert login_response.status_code == 200

        detail_response = await client.get(f"/dashboard/clients/{created_client.id}")
        rotate_response = await client.post(f"/v1/admin/clients/{created_client.id}/keys", json={})
        revoke_response = await client.post(f"/v1/admin/clients/{created_client.id}/keys/revoke", json={})
        detail_after_revoke = await client.get(f"/dashboard/clients/{created_client.id}")
        preflight_after_revoke = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": original_client_key},
        )

    assert detail_response.status_code == 200
    assert "Client Registry" in detail_response.text

    assert rotate_response.status_code == 201
    assert rotate_response.json()["client_api_key"].startswith("mkc_")

    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked"] is True

    assert detail_after_revoke.status_code == 200
    assert preflight_after_revoke.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_client_detail_shows_recent_activity_and_connection_test(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin_user, api_key = await auth.register_user(
        email="activity-admin@example.com",
        username="activity_admin",
        display_name="Activity Admin",
        role=UserRole.ADMIN,
    )
    created_client, original_client_key = await auth.register_client(
        name="Activity Client",
        slug="activity-client",
        created_by_user_id=admin_user.id,
        tool_scopes=["minder_query"],
        repo_scopes=["/workspace/repo"],
    )
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login_response = await client.post("/v1/admin/login", json={"api_key": api_key})
        assert login_response.status_code == 200

        rotate_response = await client.post(f"/v1/admin/clients/{created_client.id}/keys", json={})
        assert rotate_response.status_code == 201

        connection_test_response = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": original_client_key},
        )
        detail_response = await client.get(f"/dashboard/clients/{created_client.id}")

    assert connection_test_response.status_code == 200
    assert connection_test_response.json()["client"]["slug"] == "activity-client"

    assert detail_response.status_code == 200
    assert "Client Registry" in detail_response.text
