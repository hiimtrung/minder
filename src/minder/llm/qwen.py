from __future__ import annotations

from pathlib import Path

from minder.graph.state import GraphState


class QwenLocalLLM:
    def __init__(
        self,
        model_path: str,
        fail: bool = False,
        runtime: str = "mock",
    ) -> None:
        self._model_path = model_path
        self._fail = fail
        self._runtime = runtime

    def generate(self, state: GraphState) -> dict[str, object]:
        if self._fail:
            raise RuntimeError("Local Qwen model unavailable")

        runtime = self._runtime
        model_exists = Path(self._model_path).expanduser().exists()
        if runtime == "auto":
            runtime = "llama_cpp" if model_exists else "mock"

        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        text = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )
        return {
            "text": text,
            "sources": source_paths,
            "provider": "qwen_local",
            "model": "Qwen3.5-0.8B",
            "model_path": self._model_path,
            "runtime": runtime,
            "stream": [line for line in text.splitlines() if line],
        }
