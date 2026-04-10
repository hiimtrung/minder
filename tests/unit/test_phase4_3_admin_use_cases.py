from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
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
async def test_admin_use_cases_create_client_and_shape_typed_payloads(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
) -> None:
    from minder.application.admin.use_cases import AdminConsoleUseCases

    admin, _ = await auth.register_user(
        email="usecase-admin@example.com",
        username="usecase_admin",
        display_name="Use Case Admin",
        role=UserRole.ADMIN,
    )
    use_cases = AdminConsoleUseCases(store=store, auth_service=auth, config=config)

    created = await use_cases.create_client(
        actor_user_id=admin.id,
        name="Typed Client",
        slug="typed-client",
        description="Created from use case",
        tool_scopes=["minder_query"],
        repo_scopes=["/workspace/repo"],
    )

    assert created["client"]["slug"] == "typed-client"
    assert created["client"]["tool_scopes"] == ["minder_query"]
    assert created["client"]["repo_scopes"] == ["/workspace/repo"]
    assert created["client_api_key"].startswith("mkc_")

    listed = await use_cases.list_clients()
    assert listed["clients"][0]["slug"] == "typed-client"


@pytest.mark.asyncio
async def test_admin_use_cases_can_create_user_and_reveal_api_key(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
) -> None:
    from minder.application.admin.use_cases import AdminConsoleUseCases

    await auth.register_user(
        email="admin-owner@example.com",
        username="admin_owner",
        display_name="Admin Owner",
        role=UserRole.ADMIN,
    )
    use_cases = AdminConsoleUseCases(store=store, auth_service=auth, config=config)

    created = await use_cases.create_user(
        username="new_admin",
        email="new-admin@example.com",
        display_name="New Admin",
        role="admin",
        password="secret-pass",
    )

    assert created["user"]["username"] == "new_admin"
    assert created["user"]["role"] == "admin"
    assert created["api_key"].startswith("mk_")


@pytest.mark.asyncio
async def test_admin_use_cases_detail_onboarding_activity_and_connection_contracts(
    store: RelationalStore,
    config: MinderConfig,
    auth: AuthService,
) -> None:
    from minder.application.admin.use_cases import AdminConsoleUseCases

    admin, _ = await auth.register_user(
        email="detail-admin@example.com",
        username="detail_admin",
        display_name="Detail Admin",
        role=UserRole.ADMIN,
    )
    client, client_api_key = await auth.register_client(
        name="Detail Client",
        slug="detail-client",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
        repo_scopes=["*"],
    )
    use_cases = AdminConsoleUseCases(store=store, auth_service=auth, config=config)

    detail = await use_cases.get_client_detail(client.id)
    assert detail["client"]["slug"] == "detail-client"

    onboarding = await use_cases.get_onboarding(client.id)
    assert onboarding["client"]["slug"] == "detail-client"
    assert "codex" in onboarding["templates"]
    assert '"servers"' in onboarding["templates"]["vscode"]
    assert '"tools"' not in onboarding["templates"]["vscode"]
    assert '"mcpServers"' not in onboarding["templates"]["vscode"]
    assert '"mcpServers"' in onboarding["templates"]["copilot_cli"]
    assert '"tools"' in onboarding["templates"]["copilot_cli"]
    assert '"mcpServers"' in onboarding["templates"]["cursor"]

    activity = await use_cases.get_recent_client_activity(client.id)
    assert activity[0]["event_type"] == "client.created"

    connection = await use_cases.test_client_connection(client_api_key)
    base_url = f"http://localhost:{config.server.port}"
    assert connection["ok"] is True
    assert connection["client"]["slug"] == "detail-client"
    assert "claude_code" in connection["templates"]
    assert "antigravity" in connection["templates"]
    assert "cursor" in connection["templates"]
    assert f'url = "{base_url}/sse"' in connection["templates"]["codex"]
    assert f'"serverUrl":"{base_url}/mcp"' in connection["templates"]["antigravity"]
    assert f'"url":"{base_url}/mcp"' in connection["templates"]["cursor"]

    with pytest.raises(LookupError):
        await use_cases.get_client_detail(uuid.uuid4())
