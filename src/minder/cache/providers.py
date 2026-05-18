"""
Cache Providers — implements ICacheProvider for runtime cache/session layer.

Provides in-memory LRU cache provider as a zero-dependency fallback.
"""

from __future__ import annotations


class LRUCacheProvider:
    """
    In-memory LRU cache provider implementing ICacheProvider.

    Used as zero-dependency fallback.
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
