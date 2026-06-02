"""
Transport Builder — Composition Root for the MCP server.

This module is the ONLY place where all layers meet:
- Infrastructure (stores, caches, LLMs)
- Application (tool services)
- Presentation (transport, handler registration)

The build_transport() function wires dependencies and registers tool handlers.
All handler logic has been extracted to bootstrap/handlers/ modules.
"""

from __future__ import annotations

from typing import Any

from minder.auth.service import AuthService
from minder.cache.providers import LRUCacheProvider
from minder.config import MinderConfig
from minder.graph import MinderGraph
from minder.presentation.http.admin.routes import build_http_routes
from minder.prompts import PromptRegistry
from minder.resources import ResourceRegistry
from minder.domain.interfaces.repositories import (
    IGraphRepository,
    IOperationalStore,
    IVectorStore,
)
from minder.domain.interfaces.cache import ICacheProvider
from minder.store.repo_state import RepoStateStore
from minder.tools.agents import AgentTools
from minder.tools.auth import AuthTools
from minder.tools.graph import GraphTools
from minder.tools.memory import MemoryTools
from minder.tools.query import QueryTools
from minder.tools.registry import TOOL_DESCRIPTIONS
from minder.tools.session import SessionTools
from minder.tools.skills import SkillTools
from minder.tools.workflow import WorkflowTools
from minder.transport import SSETransport, StdioTransport

# Handler modules (extracted from this file)
from minder.bootstrap.handlers.auth_handlers import (
    create_auth_handlers,
    AUTH_TOOL_AUTH_REQUIREMENTS,
)
from minder.bootstrap.handlers.session_handlers import create_session_handlers
from minder.bootstrap.handlers.memory_handlers import create_memory_handlers
from minder.bootstrap.handlers.workflow_handlers import create_workflow_handlers
from minder.bootstrap.handlers.skill_handlers import create_skill_handlers
from minder.bootstrap.handlers.search_handlers import create_search_handlers
from minder.bootstrap.handlers.agent_handlers import create_agent_handlers


def build_transport(
    *,
    config: MinderConfig,
    store: IOperationalStore,
    vector_store: IVectorStore,
    graph_store: IGraphRepository | None = None,
    cache: ICacheProvider | None = None,
) -> SSETransport | StdioTransport:
    """
    Composition Root — wires all dependencies and registers MCP tools.

    This function is intentionally the ONLY place that knows about all
    concrete implementations. It satisfies the Clean Architecture principle
    that the composition root lives at the outermost layer.
    """

    # ── Infrastructure Wiring ─────────────────────────────────────────
    auth_service = AuthService(store, config, cache=cache)
    cache_provider = cache or LRUCacheProvider()
    repo_state_store = RepoStateStore(config.workflow.repo_state_dir)

    # ── Application Services (Tool Classes) ──────────────────────────
    agent_tools = AgentTools(store)
    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    memory_tools = MemoryTools(store, config)
    skill_tools = SkillTools(store, config)
    graph_tools = GraphTools(graph_store, store)
    shared_graph = MinderGraph(store, config, graph_tools=graph_tools)
    workflow_tools = WorkflowTools(
        store,
        repo_state_store,
        graph=shared_graph,
        config=config,
    )
    query_tools = QueryTools(
        store,
        config,
        graph=shared_graph,
        vector_store=vector_store,
        graph_tools=graph_tools,
    )

    # ── Transport Selection ──────────────────────────────────────────
    transport: SSETransport | StdioTransport
    if config.server.transport == "stdio":
        transport = StdioTransport(
            config=config,
            auth_service=auth_service,
            cache_provider=cache_provider,
            store=store,
        )
    else:
        transport = SSETransport(
            config=config,
            store=store,
            auth_service=auth_service,
            extra_routes=[],
            cache_provider=cache_provider,
        )

        async def sync_prompts() -> None:
            await PromptRegistry.sync(transport.app, store)

        transport.extend_routes(
            build_http_routes(
                config=config,
                store=store,
                graph_store=graph_store,
                cache=cache,
                prompt_sync_hook=sync_prompts,
            )
        )

    # ── Create Handler Functions ─────────────────────────────────────
    all_handlers: dict[str, Any] = {}
    auth_requirements: dict[str, bool] = {}

    # Auth handlers
    auth_handlers = create_auth_handlers(auth_tools)
    all_handlers.update(auth_handlers)
    auth_requirements.update(AUTH_TOOL_AUTH_REQUIREMENTS)

    # Session handlers
    session_handlers = create_session_handlers(session_tools, store)
    all_handlers.update(session_handlers)

    # Memory handlers
    memory_handlers = create_memory_handlers(memory_tools, store=store)
    all_handlers.update(memory_handlers)

    # Workflow handlers
    workflow_handlers = create_workflow_handlers(workflow_tools, store)
    all_handlers.update(workflow_handlers)

    # Skill handlers
    skill_handlers = create_skill_handlers(skill_tools, store=store)
    all_handlers.update(skill_handlers)

    # Search handlers
    search_handlers = create_search_handlers(query_tools, graph_tools)
    all_handlers.update(search_handlers)

    # Agent handlers
    agent_handlers_map = create_agent_handlers(agent_tools)
    all_handlers.update(agent_handlers_map)

    # ── Register All Tools ───────────────────────────────────────────
    for tool_name, handler in all_handlers.items():
        require_auth = auth_requirements.get(tool_name, True)
        description = TOOL_DESCRIPTIONS.get(tool_name, "")
        transport.register_tool(
            tool_name,
            handler,
            require_auth=require_auth,
            description=description,
        )

    # ── Register Resources & Prompts ─────────────────────────────────
    ResourceRegistry.register(transport.app, store, graph_store=graph_store)
    PromptRegistry.register(transport.app, store=store)
    return transport
