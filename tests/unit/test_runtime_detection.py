import pytest

import minder.graph.executor as executor_module
import minder.graph.graph as graph_module
import minder.graph.runtime as graph_runtime_module
import minder.llm.openai as openai_module
from minder.config import MinderConfig
from minder.graph.executor import (
    GraphNodes,
    InternalGraphExecutor,
    LangGraphExecutorAdapter,
)
from minder.graph.graph import MinderGraph
from minder.graph.nodes import (
    EvaluatorNode,
    GuardNode,
    LLMNode,
    PlanningNode,
    ReasoningNode,
    RetrieverNode,
    VerificationNode,
    WorkflowPlannerNode,
)
from minder.graph.runtime import graph_runtime_name
from minder.graph.state import GraphState
from minder.llm.litert import LiteRTModelLLM
from minder.llm.openai import OpenAIFallbackLLM
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def test_graph_runtime_reports_supported_mode() -> None:
    assert graph_runtime_name() in {"internal", "langgraph"}



def test_openai_runtime_auto_reports_supported_mode() -> None:
    llm = OpenAIFallbackLLM("key", "gpt-4o-mini", runtime="auto")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
                "retrieved_docs": [],
                "workflow_context": {},
                "query": "hello",
            },
        )()
    )
    assert result["runtime"] in {"mock", "litellm"}


# llama_cpp tests removed since the dependency was removed.


def test_openai_litellm_path_uses_loaded_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_completion(**kwargs):  # noqa: ANN003
        return {"choices": [{"message": {"content": "litellm output"}}]}

    monkeypatch.setattr(openai_module, "module_available", lambda name: True)
    monkeypatch.setattr(
        openai_module, "load_attr", lambda module, attr: fake_completion
    )

    llm = OpenAIFallbackLLM("key", "gpt-4o-mini", runtime="litellm")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
                "retrieved_docs": [],
                "workflow_context": {},
                "reasoning_output": {"prompt": "hello"},
                "query": "hello",
            },
        )()
    )
    assert result["runtime"] == "litellm"
    assert result["text"] == "litellm output"


@pytest.fixture
async def store() -> RelationalStore:
    backend = RelationalStore(IN_MEMORY_URL)
    await backend.init_db()
    yield backend
    await backend.dispose()


@pytest.mark.asyncio
async def test_internal_executor_sets_internal_runtime(store: RelationalStore) -> None:
    nodes = GraphNodes(
        workflow_planner=WorkflowPlannerNode(store),
        planning=PlanningNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=LiteRTModelLLM()),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )
    state = GraphState(query="hello", repo_path=".")
    state = await InternalGraphExecutor(nodes).run(state)
    assert state.metadata["orchestration_runtime"] == "internal"


@pytest.mark.asyncio
async def test_langgraph_adapter_reports_detected_runtime(
    store: RelationalStore,
) -> None:
    nodes = GraphNodes(
        workflow_planner=WorkflowPlannerNode(store),
        planning=PlanningNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=LiteRTModelLLM()),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )
    state = GraphState(query="hello", repo_path=".")
    state = await LangGraphExecutorAdapter(nodes).run(state)
    assert state.metadata["orchestration_runtime"] in {"internal", "langgraph"}


@pytest.mark.asyncio
async def test_langgraph_adapter_uses_stategraph_when_available(
    monkeypatch: pytest.MonkeyPatch,
    store: RelationalStore,
) -> None:
    class FakeCompiledGraph:
        async def ainvoke(self, state: GraphState) -> GraphState:
            state.metadata["fake_langgraph"] = True
            return state

    class FakeStateGraph:
        def __init__(self, state_type) -> None:  # noqa: ANN001
            self.state_type = state_type

        def add_node(self, name: str, node) -> None:  # noqa: ANN001
            self.name = name
            self.node = node

        def set_entry_point(self, name: str) -> None:
            self.entry = name

        def set_finish_point(self, name: str) -> None:
            self.finish = name

        def compile(self) -> FakeCompiledGraph:
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

    nodes = GraphNodes(
        workflow_planner=WorkflowPlannerNode(store),
        planning=PlanningNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=LiteRTModelLLM()),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )
    state = GraphState(query="hello", repo_path=".")
    state = await LangGraphExecutorAdapter(nodes).run(state)
    assert state.metadata["orchestration_runtime"] == "langgraph"
    assert state.metadata["fake_langgraph"] is True


@pytest.mark.asyncio
async def test_minder_graph_defaults_to_auto_runtimes(
    monkeypatch: pytest.MonkeyPatch,
    store: RelationalStore,
) -> None:
    captured: dict[str, object] = {}

    class CapturedLLM:
        def __init__(self) -> None:
            pass

        def generate(self, state):  # noqa: ANN001, ANN201
            return {
                "text": "ok",
                "sources": [],
                "provider": "litert_lm",
                "model": "gemma-4-E2B-it",
                "runtime": "mock",
                "stream": ["ok"],
            }

    class CaptureFallback:
        def __init__(
            self, api_key: str | None, model: str, runtime: str = "mock"
        ) -> None:
            captured["fallback_runtime"] = runtime

        def available(self) -> bool:
            return False

    def fake_create_llm(config):  # noqa: ANN001, ANN201
        captured["provider"] = config.provider
        captured["context_length"] = config.context_length
        return CapturedLLM()

    monkeypatch.setattr(graph_module, "create_llm", fake_create_llm)
    monkeypatch.setattr(graph_module, "OpenAIFallbackLLM", CaptureFallback)

    MinderGraph(store, MinderConfig())

    assert captured["provider"] == "litert"
    assert captured["context_length"] == MinderConfig().llm.context_length
    assert captured["fallback_runtime"] == "auto"
