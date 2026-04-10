from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.server import build_http_app
from minder.transport import SSETransport
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


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


@pytest.mark.asyncio
async def test_phase4_gateway_auth_e2e(
    tmp_path: Path,
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    auth: AuthService,
) -> None:
    admin, _ = await auth.register_user(
        email="phase4-admin@example.com",
        username="phase4_admin",
        display_name="Phase 4 Admin",
        role=UserRole.ADMIN,
    )
    admin_token = auth.issue_jwt(admin)
    app = build_http_app(config=config, store=store, cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        create_response = await client.post(
            "/v1/admin/clients",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Codex Team",
                "slug": "codex-team",
                "description": "Primary Codex integration",
                "tool_scopes": ["minder_query", "minder_search_code", "inspect_principal"],
                "repo_scopes": [str(tmp_path)],
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        client_id = created["client"]["id"]
        client_api_key = created["client_api_key"]

        dashboard_response = await client.get(
            "/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"},
            follow_redirects=False,
        )
        assert dashboard_response.status_code == 303
        assert dashboard_response.headers["location"] == "/dashboard/clients"

        onboarding_response = await client.get(
            f"/v1/admin/onboarding/{client_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert onboarding_response.status_code == 200
        onboarding = onboarding_response.json()
        assert "codex" in onboarding["templates"]
        assert "[mcp_servers.minder]" in onboarding["templates"]["codex"]
        assert "antigravity" in onboarding["templates"]

        preflight_response = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": client_api_key},
        )
        assert preflight_response.status_code == 200
        assert preflight_response.json()["ok"] is True
        assert "http://testserver/sse" in preflight_response.json()["templates"]["vscode"]
        assert '"servers"' in preflight_response.json()["templates"]["vscode"]
        assert '"tools"' not in preflight_response.json()["templates"]["vscode"]
        assert "http://testserver/sse" in preflight_response.json()["templates"]["copilot_cli"]
        assert '"mcpServers"' in preflight_response.json()["templates"]["copilot_cli"]
        assert '"serverUrl":"http://testserver/mcp"' in preflight_response.json()["templates"]["antigravity"]
        assert "claude_code" in preflight_response.json()["templates"]

        exchange_response = await client.post(
            "/v1/auth/token-exchange",
            json={
                "client_api_key": client_api_key,
                "requested_scopes": ["minder_query", "inspect_principal"],
            },
        )
        assert exchange_response.status_code == 200
        access_token = exchange_response.json()["access_token"]

    transport = SSETransport(config=config, auth_service=auth)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "scopes": principal.scopes,
        }

    transport.register_tool("inspect_principal", inspect_principal, require_auth=True)
    protected_result = await transport.call_tool(
        "inspect_principal",
        authorization=f"Bearer {access_token}",
    )
    assert protected_result["principal_type"] == "client"
    assert protected_result["scopes"] == ["minder_query", "inspect_principal"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        revoke_response = await client.post(
            f"/v1/admin/clients/{client_id}/keys/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert revoke_response.status_code == 200
        assert revoke_response.json()["revoked"] is True

        post_revoke_preflight = await client.post(
            "/v1/gateway/test-connection",
            json={"client_api_key": client_api_key},
        )
        assert post_revoke_preflight.status_code == 401

        audit_response = await client.get(
            "/v1/admin/audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert audit_response.status_code == 200
        events = audit_response.json()["events"]
        event_types = {event["event_type"] for event in events}
        assert "client.created" in event_types
        assert "client.token_exchanged" in event_types
        assert "client.key_revoked" in event_types
