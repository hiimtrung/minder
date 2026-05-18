from __future__ import annotations

from typing import Any

import pytest

import minder.graph.executor as executor_module
import minder.graph.runtime as graph_runtime_module
from minder.config import GraphConfig, MinderConfig
from minder.graph.executor import GraphNodes, LangGraphExecutorAdapter
from minder.graph.nodes import (
    ClarificationNode,
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.state import GraphState
from minder.llm.llama_cpp_llm import LlamaCppLLM
from minder.store.relational import RelationalStore


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore("sqlite+aiosqlite:///:memory:")
    await backend.init_db()
    yield backend
    await backend.dispose()


def _build_nodes(store: RelationalStore) -> GraphNodes:
    return GraphNodes(
        workflow_planner=WorkflowPlannerNode(store),
        planning=PlanningNode(),
        clarification=ClarificationNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=LlamaCppLLM("repo", "file", runtime="mock")),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )


@pytest.mark.asyncio
async def test_checkpointing_is_gated_by_config(
    monkeypatch: pytest.MonkeyPatch,
    store: RelationalStore,
) -> None:
    compile_kwargs: list[dict[str, Any]] = []

    class FakeCompiledGraph:
        async def ainvoke(
            self, state: dict[str, Any], config: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            del config
            state["metadata"] = {
                **dict(state.get("metadata", {}) or {}),
                "compiled": True,
            }
            return state

    class FakeStateGraph:
        def __init__(self, state_type) -> None:  # noqa: ANN001
            self.state_type = state_type

        def add_node(self, name: str, node) -> None:  # noqa: ANN001
            del name, node

        def add_edge(self, source: str, target: str) -> None:
            del source, target

        def add_conditional_edges(
            self, source: str, path: object, path_map: object = None
        ) -> None:
            del source, path, path_map

        def set_entry_point(self, name: str) -> None:
            del name

        def compile(self, **kwargs: Any) -> FakeCompiledGraph:
            compile_kwargs.append(kwargs)
            return FakeCompiledGraph()

    monkeypatch.setattr(
        graph_runtime_module,
        "graph_runtime_name",
        lambda preferred="langgraph": "langgraph",
    )
    monkeypatch.setattr(
        graph_runtime_module, "load_langgraph_state_graph", lambda: FakeStateGraph
    )
    monkeypatch.setattr(
        executor_module, "graph_runtime_name", lambda preferred="langgraph": "langgraph"
    )
    monkeypatch.setattr(
        executor_module, "load_langgraph_state_graph", lambda: FakeStateGraph
    )

    enabled = MinderConfig()
    enabled.graph = GraphConfig(enable_checkpointing=True)
    await LangGraphExecutorAdapter(_build_nodes(store), store, enabled).run(
        GraphState(query="x")
    )

    disabled = MinderConfig()
    disabled.graph = GraphConfig(enable_checkpointing=False)
    await LangGraphExecutorAdapter(_build_nodes(store), store, disabled).run(
        GraphState(query="x")
    )

    assert "checkpointer" in compile_kwargs[0]
    assert "checkpointer" not in compile_kwargs[1]
