from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from minder.bootstrap.providers import build_cache, build_store, build_vector_store
from minder.bootstrap.transport import build_transport
from minder.config import Settings
from minder.embedding.qwen import QwenEmbeddingProvider
from minder.graph.runtime import graph_runtime_name
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM
from minder.presentation.http.admin.routes import build_http_app, build_http_routes

__all__ = [
    "build_cache",
    "build_http_app",
    "build_http_routes",
    "build_store",
    "build_transport",
    "build_vector_store",
    "main",
    "runtime_summary",
]


def runtime_summary(config: Settings) -> dict[str, object]:
    llm = QwenLocalLLM(config.llm.model_path, runtime="auto")
    embedder = QwenEmbeddingProvider(
        config.embedding.model_path,
        dimensions=config.embedding.dimensions,
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
        "llm_runtime_effective": llm.runtime,
        "embedding_model_path": str(Path(config.embedding.model_path).expanduser()),
        "embedding_runtime_effective": embedder.runtime,
        "openai_fallback_configured": fallback.available(),
        "openai_fallback_runtime_effective": fallback.runtime,
    }


async def _async_run() -> None:
    print("MINDER SERVER STARTING", file=sys.stderr, flush=True)
    config = Settings()

    # Initialise structured JSON logging and tracing before anything else
    from minder.observability import configure_json_logging, configure_tracing
    configure_json_logging(level=config.server.log_level)
    configure_tracing(
        service_name=config.server.name,
        service_version=config.server.version,
    )

    store = build_store(config)
    print(f"MINDER DB URL: {config.relational_store.db_path}", file=sys.stderr, flush=True)
    await store.init_db()

    vector_store = build_vector_store(config, store)
    if hasattr(vector_store, "setup"):
        await vector_store.setup()

    cache = build_cache(config)
    admin = await store.get_user_by_username("admin")
    print(f"MINDER ADMIN EXISTS: {admin is not None}", file=sys.stderr, flush=True)

    transport = build_transport(config=config, store=store, vector_store=vector_store, cache=cache)
    print(
        f"Minder store={config.relational_store.provider} cache={config.cache.provider} "
        f"transport={transport.transport_name} host={config.server.host}:{config.server.port}",
        file=sys.stderr,
        flush=True,
    )
    print("Minder runtime summary:", runtime_summary(config), file=sys.stderr, flush=True)

    try:
        if transport.transport_name == "stdio":
            await transport.app.run_stdio_async()
        else:
            print(f"Starting SSE on {config.server.host}:{config.server.port}", file=sys.stderr, flush=True)
            if hasattr(transport, "run"):
                await transport.run()
            else:
                await transport.app.run_sse_async()
    finally:
        await store.dispose()
        await cache.close()


def _run() -> None:
    asyncio.run(_async_run())


def main() -> None:
    _run()


if __name__ == "__main__":
    main()
