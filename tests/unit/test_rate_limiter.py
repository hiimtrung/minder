from __future__ import annotations

import uuid

import pytest

from minder.auth.principal import AdminUserPrincipal, ClientPrincipal
from minder.auth.rate_limiter import RateLimitError, RateLimiter
from minder.auth.service import AuthService, UserRole
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.fixture
def config() -> MinderConfig:
    settings = MinderConfig()
    settings.rate_limit.enabled = True
    settings.rate_limit.window_seconds = 60
    settings.rate_limit.member_limit = 2
    settings.rate_limit.admin_limit = 4
    settings.rate_limit.readonly_limit = 1
    settings.rate_limit.client_limit = 2
    return settings


@pytest.fixture
def cache() -> LRUCacheProvider:
    return LRUCacheProvider()


@pytest.fixture
def limiter(config: MinderConfig, cache: LRUCacheProvider) -> RateLimiter:
    return RateLimiter(cache=cache, config=config)


@pytest.mark.asyncio
async def test_member_limit_exceeded_after_configured_threshold(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    limiter: RateLimiter,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    user, _ = await auth.register_user(
        email="member-limit@example.com",
        username="member_limit",
        display_name="Member Limit",
        role=UserRole.MEMBER,
    )
    principal = AdminUserPrincipal(user)

    first = await limiter.enforce(principal=principal, tool_name="minder_query")
    second = await limiter.enforce(principal=principal, tool_name="minder_query")
    assert first.remaining == 1
    assert second.remaining == 0

    with pytest.raises(RateLimitError) as exc:
        await limiter.enforce(principal=principal, tool_name="minder_query")

    assert exc.value.code == "AUTH_RATE_LIMITED"


@pytest.mark.asyncio
async def test_admin_gets_higher_limit_than_member(
    store: RelationalStore,
    config: MinderConfig,
    cache: LRUCacheProvider,
    limiter: RateLimiter,
) -> None:
    auth = AuthService(store=store, config=config, cache=cache)
    admin, _ = await auth.register_user(
        email="admin-limit@example.com",
        username="admin_limit",
        display_name="Admin Limit",
        role=UserRole.ADMIN,
    )
    principal = AdminUserPrincipal(admin)

    for _ in range(config.rate_limit.admin_limit):
        await limiter.enforce(principal=principal, tool_name="minder_query")

    usage = await limiter.get_usage(principal=principal, tool_name="minder_query")
    assert usage["count"] == config.rate_limit.admin_limit
    assert usage["limit"] == config.rate_limit.admin_limit


@pytest.mark.asyncio
async def test_client_limit_is_tracked_separately(
    config: MinderConfig,
    limiter: RateLimiter,
) -> None:
    principal = ClientPrincipal(
        client_id=uuid.uuid4(),
        client_slug="client-one",
        scopes=["minder_query"],
        repo_scope=[],
    )

    await limiter.enforce(principal=principal, tool_name="minder_query")
    usage = await limiter.get_usage(principal=principal, tool_name="minder_query")
    assert usage["count"] == 1
    assert usage["limit"] == config.rate_limit.client_limit
