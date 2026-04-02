from minder.graph.runtime import graph_runtime_name
from minder.llm.openai import OpenAIFallbackLLM
from minder.llm.qwen import QwenLocalLLM


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
