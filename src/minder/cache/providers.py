"""
Redis Cache Provider — implements ICacheProvider for runtime cache/session layer.

Provides async cache operations backed by Redis. Supports key-value storage,
TTL, namespaced operations, and health checks.
"""

from __future__ import annotations

import redis.asyncio as aioredis


class RedisCacheProvider:
    """Async Redis cache provider implementing ICacheProvider."""

    def __init__(
        self,
        uri: str = "redis://localhost:6379/0",
        *,
        prefix: str = "minder:",
        default_ttl: int = 3600,
    ) -> None:
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._client: aioredis.Redis = aioredis.from_url(  # type: ignore[type-arg]
            uri,
            decode_responses=True,
        )

    def _key(self, key: str) -> str:
        """Apply namespace prefix to key."""
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        result = await self._client.get(self._key(key))
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return result  # type: ignore[return-value]

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        """Set a key-value pair with optional TTL."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        await self._client.set(self._key(key), value, ex=effective_ttl)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self._client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return bool(await self._client.exists(self._key(key)))

    async def expire(self, key: str, ttl: int) -> None:
        """Set expiration on an existing key."""
        await self._client.expire(self._key(key), ttl)

    async def incr(self, key: str) -> int:
        """Increment an integer value."""
        result = await self._client.incr(self._key(key))
        return int(result)

    async def keys(self, pattern: str) -> list[str]:
        """Get keys matching a pattern (within namespace)."""
        full_pattern = self._key(pattern)
        raw_keys: list[str] = await self._client.keys(full_pattern)  # type: ignore[assignment]
        prefix_len = len(self._prefix)
        return [k[prefix_len:] if k.startswith(self._prefix) else k for k in raw_keys]

    async def flush_namespace(self, namespace: str) -> None:
        """Delete all keys under a specific namespace prefix."""
        pattern = self._key(f"{namespace}:*")
        raw_keys = await self._client.keys(pattern)
        if raw_keys:
            await self._client.delete(*raw_keys)

    async def health_check(self) -> bool:
        """Ping Redis to check connectivity."""
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._client.aclose()


class LRUCacheProvider:
    """
    In-memory LRU cache provider implementing ICacheProvider.

    Used as zero-dependency fallback when Redis is not available.
    """

    def __init__(self, *, max_size: int = 1000, default_ttl: int = 3600) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        if len(self._store) >= self._max_size:
            # Evict oldest entry (FIFO as simple approximation)
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def expire(self, key: str, ttl: int) -> None:
        pass  # No-op for in-memory store

    async def incr(self, key: str) -> int:
        current = int(self._store.get(key, "0"))
        current += 1
        self._store[key] = str(current)
        return current

    async def keys(self, pattern: str) -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def flush_namespace(self, namespace: str) -> None:
        prefix = f"{namespace}:"
        to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in to_delete:
            del self._store[k]

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        self._store.clear()
