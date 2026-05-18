"""
Cache package — providers for runtime caching layer.
"""

from minder.cache.providers import LRUCacheProvider

__all__ = [
    "LRUCacheProvider",
    "RedisCacheProvider",
]


def __getattr__(name: str):  # type: ignore[misc]
    if name == "RedisCacheProvider":
        from minder.cache.providers import RedisCacheProvider
        return RedisCacheProvider
    raise AttributeError(name)
