import pytest

from minder.auth.service import AuthService, ClientPrincipal, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.store.relational import RelationalStore
from minder.tools.auth import AuthTools

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
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


@pytest.fixture
def auth_tools(store: RelationalStore, auth: AuthService) -> AuthTools:
    return AuthTools(store, auth)


@pytest.mark.asyncio
async def test_register_client_returns_client_and_bootstrap_key(auth: AuthService) -> None:
    admin, _ = await auth.register_user(
        email="admin.phase4@example.com",
        username="admin_phase4",
        display_name="Admin",
        role=UserRole.ADMIN,
    )

    client, client_api_key = await auth.register_client(
        name="Codex Local",
        slug="codex-local",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query", "minder_search_code"],
        repo_scopes=["/workspace/repo"],
    )

    assert client.name == "Codex Local"
    assert client.slug == "codex-local"
    assert client.tool_scopes == ["minder_query", "minder_search_code"]
    assert client_api_key.startswith("mkc_")


@pytest.mark.asyncio
async def test_exchange_client_api_key_returns_short_lived_access_token(
    auth: AuthService,
) -> None:
    admin, _ = await auth.register_user(
        email="admin.exchange@example.com",
        username="admin_exchange",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    client, client_api_key = await auth.register_client(
        name="Codex Local",
        slug="codex-local",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query", "minder_search_code"],
    )

    exchange = await auth.exchange_client_api_key(
        client_api_key,
        requested_scopes=["minder_query"],
    )

    assert exchange["token_type"] == "Bearer"
    assert exchange["client_id"] == str(client.id)
    assert exchange["access_token"]
    principal = await auth.get_principal_from_token(exchange["access_token"])
    assert isinstance(principal, ClientPrincipal)
    assert principal.client_id == client.id
    assert principal.scopes == ["minder_query"]


@pytest.mark.asyncio
async def test_client_exchange_tool_is_admin_and_client_friendly(
    auth: AuthService,
    auth_tools: AuthTools,
) -> None:
    admin, _ = await auth.register_user(
        email="admin.tools@example.com",
        username="admin_tools",
        display_name="Admin",
        role=UserRole.ADMIN,
    )

    created = await auth_tools.minder_auth_create_client(
        actor_user_id=admin.id,
        name="VS Code Copilot",
        slug="copilot-local",
        tool_scopes=["minder_query"],
    )
    assert created["client"]["slug"] == "copilot-local"
    assert created["client_api_key"].startswith("mkc_")

    exchanged = await auth_tools.minder_auth_exchange_client_key(
        created["client_api_key"],
        requested_scopes=["minder_query"],
    )
    assert exchanged["token_type"] == "Bearer"
    assert exchanged["client_id"] == created["client"]["id"]


@pytest.mark.asyncio
async def test_revoked_client_key_cannot_exchange(auth: AuthService) -> None:
    admin, _ = await auth.register_user(
        email="admin.revoke@example.com",
        username="admin_revoke",
        display_name="Admin",
        role=UserRole.ADMIN,
    )
    client, client_api_key = await auth.register_client(
        name="Claude Desktop",
        slug="claude-desktop",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
    )
    await auth.revoke_client_api_keys(client.id)

    with pytest.raises(Exception) as exc:
        await auth.exchange_client_api_key(client_api_key)

    assert getattr(exc.value, "code", None) == "AUTH_INVALID_CLIENT_KEY"
