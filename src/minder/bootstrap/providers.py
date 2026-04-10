from __future__ import annotations

from pathlib import Path

from minder.cache.providers import LRUCacheProvider, RedisCacheProvider
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore, IVectorStore
from minder.store.relational import RelationalStore
from minder.store.vector import VectorStore


def build_store(config: MinderConfig) -> IOperationalStore:
    provider = config.relational_store.provider

    if provider == "mongodb":
        from minder.store.mongodb.client import MongoClient
        from minder.store.mongodb.operational_store import MongoOperationalStore

        client = MongoClient(
            uri=config.mongodb.uri,
            database=config.mongodb.database,
            min_pool_size=config.mongodb.min_pool_size,
            max_pool_size=config.mongodb.max_pool_size,
        )
        return MongoOperationalStore(client)  # type: ignore[return-value]

    db_path = config.relational_store.db_path
    if db_path.startswith(("sqlite+", "postgresql+", "postgres://")):
        db_url = db_path
    else:
        expanded = Path(db_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{expanded}"
    return RelationalStore(db_url)  # type: ignore[return-value]


def build_cache(config: MinderConfig) -> ICacheProvider:
    if config.cache.provider == "redis":
        return RedisCacheProvider(
            uri=config.redis.uri,
            prefix=config.redis.prefix,
            default_ttl=config.redis.cache_ttl,
        )
    return LRUCacheProvider(
        max_size=config.cache.max_size,
        default_ttl=config.cache.ttl_seconds,
    )


def build_vector_store(config: MinderConfig, store: IOperationalStore) -> IVectorStore:
    if config.vector_store.provider == "milvus":
        from minder.store.milvus.client import MilvusClient
        from minder.store.milvus.vector_store import MilvusVectorStore

        client = MilvusClient(uri=config.vector_store.uri)
        return MilvusVectorStore(
            client,
            store,
            prefix=config.vector_store.collection_prefix,
            dimensions=config.embedding.dimensions,
        )

    return VectorStore(store, store)
