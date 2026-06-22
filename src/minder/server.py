from __future__ import annotations

import asyncio
import sys

from minder.bootstrap.agent_seeder import seed_default_agents
from minder.bootstrap.workflow_seeder import seed_default_workflows
from minder.infrastructure.model_bootstrap import ensure_models_available
from minder.bootstrap.providers import (
    build_cache,
    build_graph_store,
    build_store,
    build_vector_store,
)
from minder.bootstrap.transport import build_transport
from minder.config import Settings
from minder.graph.runtime import graph_runtime_name
from minder.presentation.http.admin.routes import build_http_app, build_http_routes

__all__ = [
    "build_cache",
    "build_graph_store",
    "build_http_app",
    "build_http_routes",
    "build_store",
    "build_transport",
    "build_vector_store",
    "main",
    "runtime_summary",
]


def runtime_summary(config: Settings) -> dict[str, object]:
    embedding_runtime = _detect_llama_cpp_runtime(config)
    openai_key_set = bool(config.llm.openai_api_key)

    return {
        "transport": config.server.transport,
        "host": config.server.host,
        "port": config.server.port,
        "orchestration_runtime_requested": config.workflow.orchestration_runtime,
        "orchestration_runtime_effective": graph_runtime_name(
            config.workflow.orchestration_runtime
        ),
        "llm_provider": config.llm.provider,
        "llm_runtime_effective": config.llm.provider,
        "llm_context_length": config.llm.context_length,
        "embedding_provider": "llama_cpp",
        "embedding_llama_cpp_model_repo": config.embedding.llama_cpp_model_repo,
        "embedding_runtime_effective": embedding_runtime,
        "openai_fallback_configured": openai_key_set,
        "openai_fallback_runtime_effective": "openai" if openai_key_set else "mock",
    }


def _detect_llama_cpp_runtime(config: Settings) -> str:
    if config.embedding.runtime == "mock":
        return "mock"
    try:
        import llama_cpp  # type: ignore[import-not-found]  # noqa: F401
        return "llama_cpp"
    except (ImportError, RuntimeError, OSError):
        # RuntimeError/OSError when the .so loads but a system lib (e.g. libgomp.so.1) is absent
        return "mock"



async def _watch_parent_process() -> None:
    import os
    import signal
    try:
        initial_ppid = os.getppid()
        if initial_ppid <= 1:
            return
        while True:
            await asyncio.sleep(2)
            if os.getppid() != initial_ppid:
                # Parent process died (adopted by init/launchd)
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception:
                    sys.exit(0)
                break
    except Exception:
        pass


async def _async_run() -> None:
    print("MINDER SERVER STARTING", file=sys.stderr, flush=True)
    asyncio.create_task(_watch_parent_process())
    config = Settings()

    # Interactive LLM setup at boot up
    from minder.infrastructure.interactive_setup import run_interactive_model_setup
    run_interactive_model_setup(config)

    # Initialise structured JSON logging and tracing before anything else
    from minder.observability import configure_json_logging, configure_tracing

    configure_json_logging(level=config.server.log_level)
    configure_tracing(
        service_name=config.server.name,
        service_version=config.server.version,
    )

    # Pre-download GGUF files so they are present in the HF cache when the
    # providers initialise below.  Runs in a background thread to avoid blocking the
    # event loop and server startup.
    asyncio.create_task(asyncio.to_thread(ensure_models_available, config))

    store = build_store(config)
    await store.init_db()
    await seed_default_agents(store)
    await seed_default_workflows(store)

    graph_store = build_graph_store(config)
    if graph_store is not None and hasattr(graph_store, "init_db"):
        await graph_store.init_db()

    vector_store = build_vector_store(config, store)
    if hasattr(vector_store, "setup"):
        await vector_store.setup()

    # Swarm coordination store — dedicated swarm.db (decision Q3)
    swarm_store = None
    if config.swarm.enabled:
        from minder.store.swarm import SwarmStore

        swarm_store = SwarmStore(db_path=config.swarm.db_path)
        await swarm_store.init_db()

    cache = build_cache(config)
    admin = await store.get_user_by_username("admin")
    print(f"MINDER ADMIN EXISTS: {admin is not None}", file=sys.stderr, flush=True)

    transport = build_transport(
        config=config,
        store=store,
        vector_store=vector_store,
        graph_store=graph_store,
        cache=cache,
        swarm_store=swarm_store,
    )

    from minder.prompts import PromptRegistry

    await PromptRegistry.sync(transport.app, store)

    print(
        f"Minder store={config.relational_store.provider} "
        f"transport={transport.transport_name} host={config.server.host}:{config.server.port}",
        file=sys.stderr,
        flush=True,
    )
    print(
        "Minder runtime summary:", runtime_summary(config), file=sys.stderr, flush=True
    )

    from minder.embedding.local import LocalEmbeddingProvider
    from minder.application.memory.service import MemoryService
    from minder.application.curator.service import SkillCurator
    from minder.learning.error_learner import ErrorLearner
    from minder.application.maintenance.scheduler import MaintenanceScheduler

    embedder = LocalEmbeddingProvider(
        llama_cpp_model_repo=config.embedding.llama_cpp_model_repo,
        llama_cpp_model_file=config.embedding.llama_cpp_model_file,
        dimensions=config.embedding.dimensions,
        runtime=config.embedding.runtime,
    )
    memory_service = MemoryService(store=store, config=config, embedder=embedder)
    curator = SkillCurator(store=store, config=config, embedder=embedder)
    error_learner = ErrorLearner(store=store, embedder=embedder)
    scheduler = MaintenanceScheduler(
        store=store,
        config=config,
        vector_store=vector_store,
        memory_service=memory_service,
        curator=curator,
        error_learner=error_learner,
    )
    scheduler.start()

    # Swarm dispatcher (S-4) — Minder-spawn model, off by default (pull-spawn first).
    swarm_dispatcher = None
    if swarm_store is not None and config.swarm.enabled and config.swarm.dispatcher_enabled:
        from minder.application.swarm.dispatcher import SwarmDispatcher
        from minder.application.swarm.service import SwarmService

        swarm_dispatcher = SwarmDispatcher(
            swarm_store, SwarmService(swarm_store, config), config
        )
        swarm_dispatcher.start()

    try:
        if transport.transport_name == "stdio":
            await transport.app.run_stdio_async()
        else:
            print(
                f"Starting SSE on {config.server.host}:{config.server.port}",
                file=sys.stderr,
                flush=True,
            )
            if hasattr(transport, "run"):
                await transport.run()
            else:
                await transport.app.run_sse_async()
    finally:
        if "scheduler" in locals() and scheduler is not None:
            await scheduler.stop()
        await store.dispose()
        if graph_store is not None and hasattr(graph_store, "dispose"):
            await graph_store.dispose()
        await cache.close()
        from minder.llm.llama_cpp_llm import clear_caches as _clear_llm
        from minder.embedding.local import clear_caches as _clear_embedding
        from minder.graph.concurrency import shutdown_pool as _shutdown_pool
        _clear_llm()
        _clear_embedding()
        _shutdown_pool()


def _run() -> None:
    asyncio.run(_async_run())


def main() -> None:
    _run()


if __name__ == "__main__":
    main()
