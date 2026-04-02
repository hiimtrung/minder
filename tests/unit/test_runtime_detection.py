import pytest

import minder.graph.executor as executor_module
import minder.graph.runtime as graph_runtime_module
import minder.llm.openai as openai_module
import minder.llm.qwen as qwen_module
import minder.embedding.qwen as qwen_embedding_module
from minder.graph.executor import GraphNodes, InternalGraphExecutor, LangGraphExecutorAdapter
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
from minder.embedding.qwen import QwenEmbeddingProvider
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def test_graph_runtime_reports_supported_mode() -> None:
    assert graph_runtime_name() in {"internal", "langgraph"}


def test_qwen_runtime_auto_reports_supported_mode() -> None:
    llm = QwenLocalLLM("~/.minder/models/qwen.gguf", runtime="auto")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
                "workflow_context": {},
                "plan": {},
                "query": "hello",
            },
        )()
    )
    assert result["runtime"] in {"mock", "llama_cpp"}


def test_openai_runtime_auto_reports_supported_mode() -> None:
    llm = OpenAIFallbackLLM("key", "gpt-4o-mini", runtime="auto")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
                "workflow_context": {},
                "query": "hello",
            },
        )()
    )
    assert result["runtime"] in {"mock", "litellm"}


def test_qwen_llama_cpp_path_uses_loaded_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

        def create_completion(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
            return {"choices": [{"text": "llama output"}]}

    monkeypatch.setattr(qwen_module, "module_available", lambda name: True)
    monkeypatch.setattr(qwen_module, "load_attr", lambda module, attr: FakeLlama)

    llm = QwenLocalLLM("/tmp/model.gguf", runtime="llama_cpp")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
                "workflow_context": {},
                "reasoning_output": {"prompt": "hello"},
                "plan": {},
                "query": "hello",
            },
        )()
    )
    assert result["runtime"] == "llama_cpp"
    assert result["text"] == "llama output"


def test_qwen_embedding_llama_cpp_path_uses_loaded_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

        def embed(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3, 0.4]

    monkeypatch.setattr(qwen_embedding_module, "module_available", lambda name: True)
    monkeypatch.setattr(qwen_embedding_module, "load_attr", lambda module, attr: FakeLlama)

    embedder = QwenEmbeddingProvider("/tmp/model.gguf", dimensions=4, runtime="llama_cpp")
    assert embedder.embed("hello") == [0.1, 0.2, 0.3, 0.4]


def test_openai_litellm_path_uses_loaded_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_completion(**kwargs):  # noqa: ANN003
        return {"choices": [{"message": {"content": "litellm output"}}]}

    monkeypatch.setattr(openai_module, "module_available", lambda name: True)
    monkeypatch.setattr(openai_module, "load_attr", lambda module, attr: fake_completion)

    llm = OpenAIFallbackLLM("key", "gpt-4o-mini", runtime="litellm")
    result = llm.generate(
        type(
            "StubState",
            (),
            {
                "reranked_docs": [],
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
        llm=LLMNode(primary=QwenLocalLLM("~/.minder/models/qwen.gguf")),
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
        llm=LLMNode(primary=QwenLocalLLM("~/.minder/models/qwen.gguf")),
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

    monkeypatch.setattr(graph_runtime_module, "graph_runtime_name", lambda preferred="langgraph": "langgraph")
    monkeypatch.setattr(graph_runtime_module, "load_langgraph_state_graph", lambda: FakeStateGraph)
    monkeypatch.setattr(executor_module, "graph_runtime_name", lambda preferred="langgraph": "langgraph")
    monkeypatch.setattr(executor_module, "load_langgraph_state_graph", lambda: FakeStateGraph)

    nodes = GraphNodes(
        workflow_planner=WorkflowPlannerNode(store),
        planning=PlanningNode(),
        retriever=RetrieverNode(top_k=1),
        reasoning=ReasoningNode(),
        llm=LLMNode(primary=QwenLocalLLM("~/.minder/models/qwen.gguf")),
        guard=GuardNode(),
        verification=VerificationNode(sandbox="subprocess"),
        evaluator=EvaluatorNode(),
    )
    state = GraphState(query="hello", repo_path=".")
    state = await LangGraphExecutorAdapter(nodes).run(state)
    assert state.metadata["orchestration_runtime"] == "langgraph"
    assert state.metadata["fake_langgraph"] is True
