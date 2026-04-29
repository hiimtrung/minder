from __future__ import annotations

from pathlib import Path

from minder.cache.providers import RedisCacheProvider
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IGraphRepository, IOperationalStore, IVectorStore
from minder.store.vector import VectorStore


def _sqlite_db_url(raw_path: str) -> str:
    db_path = Path(raw_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


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
            db_url = _sqlite_db_url(config.relational_store.db_path)
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


def build_graph_store(config: MinderConfig) -> IGraphRepository | None:
    if not config.graph_store.enabled:
        return None

    provider = config.graph_store.provider
    if provider == "auto":
        provider = config.relational_store.provider

    if provider == "mongodb":
        from minder.store.mongodb.client import MongoClient
        from minder.store.mongodb.graph_store import MongoGraphStore

        client = MongoClient(
            uri=config.mongodb.uri,
            database=config.mongodb.database,
            min_pool_size=config.mongodb.min_pool_size,
            max_pool_size=config.mongodb.max_pool_size,
        )
        return MongoGraphStore(client)  # type: ignore[return-value]

    if provider in ("sqlite", "postgresql"):
        from minder.store.graph import KnowledgeGraphStore

        if provider == "sqlite":
            if config.graph_store.provider == "auto" and config.relational_store.provider == "sqlite":
                db_url = _sqlite_db_url(config.relational_store.db_path)
            else:
                db_url = _sqlite_db_url(config.graph_store.db_path)
        else:
            if config.graph_store.provider == "auto" and config.relational_store.provider == "postgresql":
                db_url = config.relational_store.uri
            else:
                db_url = config.graph_store.uri

        return KnowledgeGraphStore(db_url)

    raise ValueError(
        f"Unsupported graph_store.provider '{provider}'. "
        "Supported: 'auto', 'mongodb', 'sqlite', 'postgresql'."
    )
