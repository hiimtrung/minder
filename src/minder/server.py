from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from minder.auth.service import AuthService
from minder.cache.providers import LRUCacheProvider, RedisCacheProvider
from minder.config import MinderConfig, Settings
from minder.embedding.qwen import QwenEmbeddingProvider
from minder.graph.runtime import graph_runtime_name
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM
from minder.store.document import DocumentStore
from minder.store.error import ErrorStore
from minder.store.interfaces import ICacheProvider, IOperationalStore, IVectorStore
from minder.store.vector import VectorStore
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.query import QueryTools
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools
from minder.tools.memory import MemoryTools
from minder.transport import SSETransport, StdioTransport


def build_store(config: MinderConfig) -> IOperationalStore:
    """Build the operational store based on config provider setting."""
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

    # Default: SQLite via SQLAlchemy
    db_path = config.relational_store.db_path
    if db_path.startswith(("sqlite+", "postgresql+", "postgres://")):
        db_url = db_path
    else:
        expanded = Path(db_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{expanded}"
    return RelationalStore(db_url)  # type: ignore[return-value]


def build_cache(config: MinderConfig) -> ICacheProvider:
    """Build the cache provider based on config."""
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
    """Build the vector store based on config provider setting."""
    
    if config.vector_store.provider == "milvus":
        from minder.store.milvus.client import MilvusClient
        from minder.store.milvus.vector_store import MilvusVectorStore
        client = MilvusClient(uri=config.vector_store.uri)
        return MilvusVectorStore(client, prefix=config.vector_store.collection_prefix)
        
    rel_store = cast(RelationalStore, store)
    doc_store = DocumentStore(rel_store)
    error_store = ErrorStore(rel_store)
    return VectorStore(doc_store, error_store)


def build_transport(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    vector_store: IVectorStore,
) -> SSETransport | StdioTransport:
    auth_service = AuthService(store, config)
    repo_state_store = RepoStateStore(config.workflow.repo_state_dir)
    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    search_tools = SearchTools(store, config)
    query_tools = QueryTools(store, config, vector_store=vector_store)

    transport: SSETransport | StdioTransport
    if config.server.transport == "stdio":
        transport = StdioTransport(config=config, auth_service=auth_service)
    else:
        transport = SSETransport(config=config, auth_service=auth_service)

    async def minder_auth_login(api_key: str) -> dict[str, str]:
        return await auth_tools.minder_auth_login(api_key)

    async def minder_auth_whoami(*, user=None) -> dict[str, Any]:  # noqa: ANN001
        token = auth_service.issue_jwt(user)
        return await auth_tools.minder_auth_whoami(token)

    async def minder_auth_manage(*, user=None, action: str) -> dict[str, object]:  # noqa: ANN001
        return await auth_tools.minder_auth_manage(actor_user_id=user.id, action=action)

    async def minder_session_create(
        *, user, repo_id: str | None = None, project_context: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        return await session_tools.minder_session_create(
            user_id=user.id,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            project_context=project_context,
        )

    async def minder_session_save(
        *, user, session_id: str, state: dict[str, Any] | None = None, active_skills: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
        )

    async def minder_session_restore(*, user, session_id: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_restore(uuid.UUID(session_id))

    async def minder_session_context(
        *, user, session_id: str, branch: str, open_files: list[str]  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_context(
            uuid.UUID(session_id),
            branch=branch,
            open_files=open_files,
        )

    async def minder_workflow_get(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_get(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_step(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_step(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_update(
        *,
        user,
        repo_id: str,
        repo_path: str,
        completed_step: str,
        artifact_name: str | None = None,
        artifact_content: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_update(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
            completed_step=completed_step,
            artifact_name=artifact_name,
            artifact_content=artifact_content,
        )

    async def minder_workflow_guard(*, user, repo_id: str, requested_step: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=uuid.UUID(repo_id),
            requested_step=requested_step,
        )

    async def minder_memory_store(
        *, user, title: str, content: str, tags: list[str], language: str  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
        )

    async def minder_memory_recall(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_recall(query, limit=limit)

    async def minder_memory_list(*, user=None) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_list()

    async def minder_memory_delete(*, user=None, skill_id: str) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_delete(skill_id)

    async def minder_search(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await search_tools.minder_search(query, limit=limit)

    async def minder_query(
        *,
        user=None,
        query: str,
        repo_path: str,
        session_id: str | None = None,
        repo_id: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        return await query_tools.minder_query(
            query,
            repo_path=repo_path,
            session_id=uuid.UUID(session_id) if session_id else None,
            user_id=user.id if user else None,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            workflow_name=workflow_name,
        )

    async def minder_search_code(*, user=None, query: str, repo_path: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_code(query, repo_path=repo_path, limit=limit)

    async def minder_search_errors(*, user=None, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_errors(query, limit=limit)

    async def minder_auth_ping(message: str) -> str:
        return f"auth pong: {message}"
    
    transport.register_tool(
        "minder_auth_ping",
        minder_auth_ping,
        require_auth=True,
        description="Verify authentication round-trip.",
    )

    transport.register_tool("minder_auth_login", minder_auth_login, require_auth=False)
    transport.register_tool("minder_auth_whoami", minder_auth_whoami, require_auth=True)
    transport.register_tool("minder_auth_manage", minder_auth_manage, require_auth=True)
    transport.register_tool("minder_session_create", minder_session_create, require_auth=True)
    transport.register_tool("minder_session_save", minder_session_save, require_auth=True)
    transport.register_tool("minder_session_restore", minder_session_restore, require_auth=True)
    transport.register_tool("minder_session_context", minder_session_context, require_auth=True)
    transport.register_tool("minder_workflow_get", minder_workflow_get, require_auth=True)
    transport.register_tool("minder_workflow_step", minder_workflow_step, require_auth=True)
    transport.register_tool("minder_workflow_update", minder_workflow_update, require_auth=True)
    transport.register_tool("minder_workflow_guard", minder_workflow_guard, require_auth=True)
    transport.register_tool("minder_memory_store", minder_memory_store, require_auth=True)
    transport.register_tool("minder_memory_recall", minder_memory_recall, require_auth=True)
    transport.register_tool("minder_memory_list", minder_memory_list, require_auth=True)
    transport.register_tool("minder_memory_delete", minder_memory_delete, require_auth=True)
    transport.register_tool("minder_search", minder_search, require_auth=True)
    transport.register_tool("minder_query", minder_query, require_auth=True)
    transport.register_tool("minder_search_code", minder_search_code, require_auth=True)
    transport.register_tool("minder_search_errors", minder_search_errors, require_auth=True)
    return transport


def runtime_summary(config: MinderConfig) -> dict[str, object]:
    llm = QwenLocalLLM(config.llm.model_path, runtime="auto")
    embedder = QwenEmbeddingProvider(
        config.embedding.model_path,
        dimensions=min(config.embedding.dimensions, 16),
        runtime="auto",
    )
    fallback = OpenAIFallbackLLM(config.llm.openai_api_key, config.llm.openai_model, runtime="auto")
    return {
        "transport": config.server.transport,
        "host": config.server.host,
        "port": config.server.port,
        "orchestration_runtime_requested": config.workflow.orchestration_runtime,
        "orchestration_runtime_effective": graph_runtime_name(config.workflow.orchestration_runtime),
        "llm_model_path": str(Path(config.llm.model_path).expanduser()),
        "llm_runtime_effective": llm.generate(
            type(
                "StubState",
                (),
                {
                    "reranked_docs": [],
                    "workflow_context": {},
                    "plan": {},
                    "query": "runtime probe",
                },
            )()
        )["runtime"],
        "embedding_model_path": str(Path(config.embedding.model_path).expanduser()),
        "embedding_runtime_effective": embedder.runtime,
        "openai_fallback_configured": fallback.available(),
        "openai_fallback_runtime_effective": fallback.runtime,
    }


def _run() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    config = Settings()
    store = build_store(config)
    vector_store = build_vector_store(config, store)
    cache = build_cache(config)

    asyncio.run(store.init_db())
    if hasattr(vector_store, "setup"):
        asyncio.run(vector_store.setup())
        
    transport = build_transport(config=config, store=store, vector_store=vector_store)
    store_type = config.relational_store.provider
    cache_type = config.cache.provider
    print(
        f"Minder store={store_type} cache={cache_type} transport={transport.transport_name} host={config.server.host}:{config.server.port}",
        file=sys.stderr,
        flush=True,
    )
    print("Minder runtime summary:", runtime_summary(config), file=sys.stderr, flush=True)
    try:
        if transport.transport_name == "stdio":
            transport.app.run(transport="stdio")
        else:
            print(f"Starting SSE on {config.server.host}:{config.server.port}", file=sys.stderr, flush=True)
            if hasattr(transport, "run"):
                asyncio.run(transport.run())
            else:
                transport.app.run(transport="sse")
    finally:
        asyncio.run(store.dispose())
        asyncio.run(cache.close())


def main() -> None:
    _run()


if __name__ == "__main__":
    main()
