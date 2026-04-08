from __future__ import annotations

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


@pytest_asyncio.fixture
async def store() -> RelationalStore:
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

    assert dashboard_response.status_code == 200
    assert "Onboarding Client" in dashboard_response.text
    assert "Client Registry" in dashboard_response.text

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
) -> None:
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/dashboard/login")

    assert response.status_code == 200
    assert "Admin Sign In" in response.text
    assert "name=\"api_key\"" in response.text


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
        login_response = await client.post(
            "/dashboard/login",
            data={"api_key": api_key},
        )

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/dashboard"
    cookie_header = login_response.headers.get("set-cookie", "")
    assert "minder_admin_token=" in cookie_header
    assert "HttpOnly" in cookie_header


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
        login_response = await client.post(
            "/dashboard/login",
            data={"api_key": api_key},
        )
        assert login_response.status_code == 303

        dashboard_response = await client.get("/dashboard")
        assert dashboard_response.status_code == 200
        assert "Cookie Dashboard Client" in dashboard_response.text

        logout_response = await client.post("/dashboard/logout")
        assert logout_response.status_code == 303
        assert logout_response.headers["location"] == "/dashboard/login"
        cleared_cookie = logout_response.headers.get("set-cookie", "")
        assert "minder_admin_token=" in cleared_cookie

        dashboard_after_logout = await client.get("/dashboard", follow_redirects=False)
        assert dashboard_after_logout.status_code == 303
        assert dashboard_after_logout.headers["location"] == "/dashboard/login"
