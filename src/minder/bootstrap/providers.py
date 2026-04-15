from __future__ import annotations

from minder.cache.providers import RedisCacheProvider
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IOperationalStore, IVectorStore
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

    if provider in ("sqlite", "postgresql"):
        from minder.store.relational import RelationalStore

        if provider == "sqlite":
            db_url = f"sqlite+aiosqlite:///{config.relational_store.db_path}"
        else:
            db_url = config.relational_store.uri

        return RelationalStore(db_url)  # type: ignore[return-value]

    raise ValueError(
        f"Unsupported relational_store.provider '{provider}'. "
        "Supported: 'mongodb', 'sqlite', 'postgresql'."
    )


def build_cache(config: MinderConfig) -> ICacheProvider:
    provider = config.cache.provider

    if provider == "redis":
        return RedisCacheProvider(
            uri=config.redis.uri,
            prefix=config.redis.prefix,
            default_ttl=config.redis.cache_ttl,
        )

    raise ValueError(
        f"Unsupported cache.provider '{provider}'. "
        "Only 'redis' is supported. Set [cache] provider = \"redis\" in minder.toml."
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
