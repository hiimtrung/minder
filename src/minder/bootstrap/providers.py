from __future__ import annotations

from pathlib import Path

from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.store.interfaces import ICacheProvider, IGraphRepository, IOperationalStore, IVectorStore
from minder.store.vector import VectorStore


def _sqlite_db_url(raw_path: str) -> str:
    db_path = Path(raw_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def build_store(config: MinderConfig) -> IOperationalStore:
    provider = config.relational_store.provider

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
        "Supported: 'sqlite', 'postgresql'."
    )


def build_cache(config: MinderConfig) -> ICacheProvider:
    return LRUCacheProvider(
        max_size=config.cache.max_size,
        default_ttl=config.cache.ttl_seconds,
    )


def build_vector_store(config: MinderConfig, store: IOperationalStore) -> IVectorStore:
    provider = config.vector_store.provider

    if provider == "turbovec":
        from minder.store.turbovec.vector_store import TurbovecVectorStore
        return TurbovecVectorStore(
            db_path=config.turbovec.db_path,
            document_store=store,  # type: ignore[arg-type]
            dimensions=config.embedding.dimensions,
        )

    if provider == "milvus":
        from minder.store.milvus.client import MilvusClientWrapper
        from minder.store.milvus.vector_store import MilvusVectorStore
        client = MilvusClientWrapper(db_path=config.milvus.db_path)
        return MilvusVectorStore(
            client,
            store,  # type: ignore[arg-type]
            dimensions=config.embedding.dimensions,
        )

    return VectorStore(store, store)  # type: ignore[arg-type]


def build_graph_store(config: MinderConfig) -> IGraphRepository | None:
    if not config.graph_store.enabled:
        return None

    provider = config.graph_store.provider
    if provider == "auto":
        provider = config.relational_store.provider

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
        "Supported: 'auto', 'sqlite', 'postgresql'."
    )
