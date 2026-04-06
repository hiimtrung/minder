"""
Unit tests for Cache Providers (Redis + LRU).

Uses fakeredis for Redis tests (no real Redis required).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from minder.cache.providers import LRUCacheProvider


# -----------------------------------------------------------------------
# Try to import fakeredis for Redis tests
# -----------------------------------------------------------------------

try:
    import fakeredis.aioredis

    _fakeredis_available = True
except ImportError:
    _fakeredis_available = False

requires_fakeredis = pytest.mark.skipif(
    not _fakeredis_available,
    reason="fakeredis not installed",
)


# -----------------------------------------------------------------------
# LRU Cache Tests (always run)
# -----------------------------------------------------------------------


class TestLRUCacheProvider:
    @pytest_asyncio.fixture
    async def cache(self) -> LRUCacheProvider:
        return LRUCacheProvider(max_size=10, default_ttl=60)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: LRUCacheProvider) -> None:
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache: LRUCacheProvider) -> None:
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache: LRUCacheProvider) -> None:
        await cache.set("key2", "value2")
        await cache.delete("key2")
        result = await cache.get("key2")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, cache: LRUCacheProvider) -> None:
        await cache.set("key3", "value3")
        assert await cache.exists("key3") is True
        assert await cache.exists("missing") is False

    @pytest.mark.asyncio
    async def test_incr(self, cache: LRUCacheProvider) -> None:
        result1 = await cache.incr("counter")
        assert result1 == 1
        result2 = await cache.incr("counter")
        assert result2 == 2

    @pytest.mark.asyncio
    async def test_keys_pattern(self, cache: LRUCacheProvider) -> None:
        await cache.set("user:1", "a")
        await cache.set("user:2", "b")
        await cache.set("session:1", "c")
        keys = await cache.keys("user:*")
        assert len(keys) == 2

    @pytest.mark.asyncio
    async def test_flush_namespace(self, cache: LRUCacheProvider) -> None:
        await cache.set("ns:key1", "a")
        await cache.set("ns:key2", "b")
        await cache.set("other:key1", "c")
        await cache.flush_namespace("ns")
        assert await cache.get("ns:key1") is None
        assert await cache.get("ns:key2") is None
        assert await cache.get("other:key1") == "c"

    @pytest.mark.asyncio
    async def test_eviction_on_max_size(self, cache: LRUCacheProvider) -> None:
        for i in range(12):
            await cache.set(f"k{i}", f"v{i}")
        # Should have evicted oldest entries
        assert len(cache._store) <= 10

    @pytest.mark.asyncio
    async def test_health_check(self, cache: LRUCacheProvider) -> None:
        assert await cache.health_check() is True

    @pytest.mark.asyncio
    async def test_close(self, cache: LRUCacheProvider) -> None:
        await cache.set("key", "value")
        await cache.close()
        assert len(cache._store) == 0


# -----------------------------------------------------------------------
# Redis Cache Tests (requires fakeredis)
# -----------------------------------------------------------------------


@requires_fakeredis
class TestRedisCacheProvider:
    @pytest_asyncio.fixture
    async def cache(self):
        """Create a RedisCacheProvider backed by fakeredis."""
        from minder.cache.providers import RedisCacheProvider

        provider = RedisCacheProvider.__new__(RedisCacheProvider)
        provider._prefix = "test:"
        provider._default_ttl = 60
        provider._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        yield provider
        await provider.close()

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: object) -> None:
        await cache.set("key1", "value1")  # type: ignore[union-attr]
        result = await cache.get("key1")  # type: ignore[union-attr]
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache: object) -> None:
        result = await cache.get("nonexistent")  # type: ignore[union-attr]
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache: object) -> None:
        await cache.set("key2", "value2")  # type: ignore[union-attr]
        await cache.delete("key2")  # type: ignore[union-attr]
        result = await cache.get("key2")  # type: ignore[union-attr]
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, cache: object) -> None:
        await cache.set("key3", "value3")  # type: ignore[union-attr]
        assert await cache.exists("key3") is True  # type: ignore[union-attr]
        assert await cache.exists("missing") is False  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_incr(self, cache: object) -> None:
        result = await cache.incr("counter")  # type: ignore[union-attr]
        assert result == 1

    @pytest.mark.asyncio
    async def test_health_check(self, cache: object) -> None:
        assert await cache.health_check() is True  # type: ignore[union-attr]
