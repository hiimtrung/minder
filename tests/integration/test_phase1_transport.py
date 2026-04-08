import pytest

from minder.auth.service import AuthService
from minder.auth.service import UserRole
from minder.config import MinderConfig
from minder.store.relational import RelationalStore
from minder.transport import SSETransport, StdioTransport

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
def auth(store: RelationalStore, config: MinderConfig) -> AuthService:
    return AuthService(store, config)


@pytest.mark.asyncio
async def test_sse_transport_rejects_missing_jwt_for_protected_tool(
    store: RelationalStore, config: MinderConfig, auth: AuthService
) -> None:
    transport = SSETransport(config=config, auth_service=auth)

    async def whoami(*, user):  # noqa: ANN001, ANN202
        return {"user_id": str(user.id), "email": user.email}

    transport.register_tool("minder_auth_whoami", whoami, require_auth=True)

    with pytest.raises(Exception) as exc:
        await transport.call_tool("minder_auth_whoami")

    assert getattr(exc.value, "code", None) == "AUTH_MISSING_TOKEN"


@pytest.mark.asyncio
async def test_sse_transport_dispatches_tool_with_authenticated_user(
    store: RelationalStore, config: MinderConfig, auth: AuthService
) -> None:
    user, _ = await auth.register_user(
        email="transport@example.com",
        username="transport",
        display_name="Transport User",
    )
    token = auth.issue_jwt(user)
    transport = SSETransport(config=config, auth_service=auth)

    async def whoami(*, user):  # noqa: ANN001, ANN202
        return {"user_id": str(user.id), "email": user.email, "role": user.role}

    transport.register_tool("minder_auth_whoami", whoami, require_auth=True)

    result = await transport.call_tool(
        "minder_auth_whoami",
        authorization=f"Bearer {token}",
    )

    assert result["email"] == "transport@example.com"
    assert result["role"] == "member"
    assert result["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_stdio_transport_uses_same_dispatch_contract(
    store: RelationalStore, config: MinderConfig, auth: AuthService
) -> None:
    user, _ = await auth.register_user(
        email="stdio@example.com",
        username="stdio",
        display_name="Stdio User",
    )
    token = auth.issue_jwt(user)
    transport = StdioTransport(config=config, auth_service=auth)

    async def echo(*, message: str, user):  # noqa: ANN001, ANN202
        return {"message": message, "user_id": str(user.id)}

    transport.register_tool("echo", echo, require_auth=True)

    result = await transport.call_tool(
        "echo",
        arguments={"message": "hello"},
        authorization=f"Bearer {token}",
    )

    assert result == {"message": "hello", "user_id": str(user.id)}
    assert "echo" in transport.list_tools()


@pytest.mark.asyncio
async def test_sse_transport_dispatches_tool_with_authenticated_client_principal(
    store: RelationalStore, config: MinderConfig
) -> None:
    auth = AuthService(store, config)
    admin, _ = await auth.register_user(
        email="principal-admin@example.com",
        username="principal_admin",
        display_name="Principal Admin",
        role=UserRole.ADMIN,
    )
    _, client_api_key = await auth.register_client(
        name="Codex Local",
        slug="codex-local",
        created_by_user_id=admin.id,
        tool_scopes=["minder_query"],
    )
    exchange = await auth.exchange_client_api_key(
        client_api_key,
        requested_scopes=["minder_query"],
    )
    transport = SSETransport(config=config, auth_service=auth)

    async def inspect_principal(*, principal):  # noqa: ANN001, ANN202
        return {
            "principal_type": principal.principal_type,
            "principal_id": str(principal.principal_id),
            "scopes": principal.scopes,
        }

    transport.register_tool("inspect_principal", inspect_principal, require_auth=True)

    result = await transport.call_tool(
        "inspect_principal",
        authorization=f"Bearer {exchange['access_token']}",
    )

    assert result["principal_type"] == "client"
    assert result["scopes"] == ["minder_query"]


@pytest.mark.asyncio
async def test_transport_enforces_rate_limit_for_member_user(
    store: RelationalStore,
    config: MinderConfig,
) -> None:
    config.rate_limit.enabled = True
    config.rate_limit.member_limit = 1
    auth = AuthService(store, config)
    user, _ = await auth.register_user(
        email="rate-user@example.com",
        username="rate_user",
        display_name="Rate User",
    )
    token = auth.issue_jwt(user)
    transport = SSETransport(config=config, auth_service=auth)

    async def echo(*, user, message: str):  # noqa: ANN001, ANN202
        return {"message": message, "user_id": str(user.id)}

    transport.register_tool("rate_echo", echo, require_auth=True)

    first = await transport.call_tool(
        "rate_echo",
        arguments={"message": "first"},
        authorization=f"Bearer {token}",
    )
    assert first["message"] == "first"

    with pytest.raises(Exception) as exc:
        await transport.call_tool(
            "rate_echo",
            arguments={"message": "second"},
            authorization=f"Bearer {token}",
        )

    assert getattr(exc.value, "code", None) == "AUTH_RATE_LIMITED"
