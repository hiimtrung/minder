from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IGraphRepository, IOperationalStore, IVectorStore
from minder.store.vector import VectorStore

if TYPE_CHECKING:
    from minder.store.qdrant.client import QdrantClientWrapper

# Single shared Qdrant client — all three stores reuse the same connection pool.
_qdrant_client: QdrantClientWrapper | None = None


def _get_qdrant_client(config: MinderConfig) -> QdrantClientWrapper:
    global _qdrant_client
    if _qdrant_client is None:
        from minder.store.qdrant.client import QdrantClientWrapper
        _qdrant_client = QdrantClientWrapper(
            url=config.qdrant.url,
            api_key=config.qdrant.api_key or None,
            prefer_grpc=config.qdrant.prefer_grpc,
            prefix=config.qdrant.collection_prefix,
        )
    return _qdrant_client


def _sqlite_db_url(raw_path: str) -> str:
    db_path = Path(raw_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def build_store(config: MinderConfig) -> IOperationalStore:
    provider = config.relational_store.provider

    if provider == "qdrant":
        from minder.store.qdrant.operational_store import QdrantOperationalStore
        return QdrantOperationalStore(_get_qdrant_client(config))  # type: ignore[return-value]

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
        db_url = (
            _sqlite_db_url(config.relational_store.db_path)
            if provider == "sqlite"
            else config.relational_store.uri
        )
        return RelationalStore(db_url)  # type: ignore[return-value]

    raise ValueError(
        f"Unsupported relational_store.provider '{provider}'. "
        "Supported: 'qdrant', 'mongodb', 'sqlite', 'postgresql'."
    )


def build_cache(config: MinderConfig) -> ICacheProvider:
    provider = config.cache.provider

    if provider == "redis":
        try:
            from minder.cache.providers import RedisCacheProvider
            return RedisCacheProvider(
                uri=config.redis.uri,
                prefix=config.redis.prefix,
                default_ttl=config.redis.cache_ttl,
            )
        except Exception:
            pass  # fall through to in-memory

    return LRUCacheProvider(
        max_size=config.cache.max_size,
        default_ttl=config.cache.ttl_seconds,
    )


def build_vector_store(config: MinderConfig, store: IOperationalStore) -> IVectorStore:
    provider = config.vector_store.provider

    if provider == "qdrant":
        from minder.store.qdrant.vector_store import QdrantVectorStore
        return QdrantVectorStore(
            _get_qdrant_client(config),
            store,  # type: ignore[arg-type]
            prefix=config.qdrant.collection_prefix,
            dimensions=config.embedding.dimensions,
        )

    if provider in ("milvus", "milvus_lite"):
        try:
            from minder.store.milvus.client import MilvusClient
            from minder.store.milvus.vector_store import MilvusVectorStore
            client = MilvusClient(uri=config.vector_store.uri if provider == "milvus" else config.vector_store.db_path)
            return MilvusVectorStore(
                client, store,
                prefix=config.vector_store.collection_prefix,
                dimensions=config.embedding.dimensions,
            )
        except ImportError:
            pass  # pymilvus not installed, fall through

    return VectorStore(store, store)  # type: ignore[arg-type]


def build_graph_store(config: MinderConfig) -> IGraphRepository | None:
    if not config.graph_store.enabled:
        return None

    provider = config.graph_store.provider
    if provider == "auto":
        provider = config.relational_store.provider

    if provider == "qdrant":
        from minder.store.qdrant.graph_store import QdrantGraphStore
        return QdrantGraphStore(_get_qdrant_client(config))  # type: ignore[return-value]

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
        "Supported: 'auto', 'qdrant', 'mongodb', 'sqlite', 'postgresql'."
    )
