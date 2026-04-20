import pytest

import minder.graph.executor as executor_module
import minder.graph.graph as graph_module
import minder.graph.runtime as graph_runtime_module
import minder.llm.local as local_llm_module
import minder.llm.openai as openai_module
import minder.embedding.local as local_embedding_module
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
from minder.embedding.local import LocalEmbeddingProvider
from minder.llm.local import LocalModelLLM
from minder.llm.openai import OpenAIFallbackLLM
from minder.store.relational import RelationalStore

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def test_graph_runtime_reports_supported_mode() -> None:
    assert graph_runtime_name() in {"internal", "langgraph"}


def test_local_model_runtime_auto_reports_supported_mode() -> None:
    llm = LocalModelLLM("~/.minder/models/local.gguf", runtime="auto")
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


def test_local_model_llama_cpp_path_uses_loaded_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

        def create_chat_completion(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
            assert kwargs["messages"][0]["content"] == "hello"
            return {
                "choices": [
                    {
                        "message": {
                            "content": "llama output\nUsing chat eos_token: <eos>\nllama_perf_context_print: total time = 1 ms"
                        }
                    }
                ]
            }

    monkeypatch.setattr(local_llm_module, "module_available", lambda name: True)
    monkeypatch.setattr(local_llm_module, "load_attr", lambda module, attr: FakeLlama)

    llm = LocalModelLLM("/tmp/model.gguf", runtime="llama_cpp", context_length=8192)
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
    assert llm._client.kwargs["verbose"] is False
    assert llm._client.kwargs["n_ctx"] == 8192


def test_local_model_llama_cpp_falls_back_to_text_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

        def create_completion(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
            assert kwargs["prompt"] == "hello"
            return {
                "choices": [
                    {
                        "text": "{{- '<turn|>\\n' -}}\nactual answer\n~llama_context: cleanup"
                    }
                ]
            }

    monkeypatch.setattr(local_llm_module, "module_available", lambda name: True)
    monkeypatch.setattr(local_llm_module, "load_attr", lambda module, attr: FakeLlama)

    llm = LocalModelLLM("/tmp/model.gguf", runtime="llama_cpp", context_length=2048)
    assert llm.complete_text("hello", fallback="fallback") == "actual answer"


def test_local_model_llama_cpp_retries_without_flash_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            if kwargs.get("flash_attn") is True:
                raise TypeError("flash_attn unsupported")
            self.kwargs = kwargs

        def create_completion(self, **kwargs) -> dict[str, object]:  # noqa: ANN003
            return {"choices": [{"text": "fallback path"}]}

    monkeypatch.setattr(local_llm_module, "module_available", lambda name: True)
    monkeypatch.setattr(local_llm_module, "load_attr", lambda module, attr: FakeLlama)

    llm = LocalModelLLM("/tmp/model.gguf", runtime="llama_cpp", context_length=131072)
    assert llm.complete_text("hello", fallback="fallback") == "fallback path"
    assert llm._client.kwargs["n_ctx"] == 131072
    assert "flash_attn" not in llm._client.kwargs


def test_local_embedding_llama_cpp_path_uses_loaded_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLlama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.kwargs = kwargs

        def embed(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3, 0.4]

    monkeypatch.setattr(local_embedding_module, "module_available", lambda name: True)
    monkeypatch.setattr(
        local_embedding_module, "load_attr", lambda module, attr: FakeLlama
    )

    embedder = LocalEmbeddingProvider(
        "/tmp/model.gguf", dimensions=4, runtime="llama_cpp"
    )
    assert embedder.embed("hello") == [0.1, 0.2, 0.3, 0.4]


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
        llm=LLMNode(primary=LocalModelLLM("~/.minder/models/local.gguf")),
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
        llm=LLMNode(primary=LocalModelLLM("~/.minder/models/local.gguf")),
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
        llm=LLMNode(primary=LocalModelLLM("~/.minder/models/local.gguf")),
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

    class CaptureLocalModel:
        def __init__(
            self,
            model_path: str,
            fail: bool = False,
            runtime: str = "mock",
            context_length: int = 4096,
        ) -> None:
            captured["local_model_runtime"] = runtime
            captured["local_model_context_length"] = context_length

        def generate(self, state):  # noqa: ANN001, ANN201
            return {
                "text": "ok",
                "sources": [],
                "provider": "local_llm",
                "model": "gemma-4-e2b-it",
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

    monkeypatch.setattr(graph_module, "LocalModelLLM", CaptureLocalModel)
    monkeypatch.setattr(graph_module, "OpenAIFallbackLLM", CaptureFallback)

    MinderGraph(store, MinderConfig())

    assert captured["local_model_runtime"] == "auto"
    assert captured["local_model_context_length"] == MinderConfig().llm.context_length
    assert captured["fallback_runtime"] == "auto"
