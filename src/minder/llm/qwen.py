from __future__ import annotations

from pathlib import Path
from typing import Any

from minder.graph.state import GraphState
from minder.runtime import load_attr, module_available


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
        self._client: Any | None = None

    def generate(self, state: GraphState) -> dict[str, object]:
        if self._fail:
            raise RuntimeError("Local Qwen model unavailable")

        runtime = self._runtime
        model_exists = Path(self._model_path).expanduser().exists()
        if runtime == "auto":
            runtime = "llama_cpp" if model_exists and module_available("llama_cpp") else "mock"

        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        text = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )
        if runtime == "llama_cpp":
            text = self._generate_with_llama_cpp(state, fallback=text)

        return {
            "text": text,
            "sources": source_paths,
            "provider": "qwen_local",
            "model": "Qwen3.5-0.8B",
            "model_path": self._model_path,
            "runtime": runtime,
            "stream": [line for line in text.splitlines() if line],
        }

    def _generate_with_llama_cpp(self, state: GraphState, *, fallback: str) -> str:
        client = self._llama_client()
        if client is None:
            return fallback

        prompt = state.reasoning_output.get("prompt") or state.query
        response = client.create_completion(
            prompt=str(prompt),
            max_tokens=256,
            temperature=0.1,
        )
        choices = response.get("choices", [])
        if not choices:
            return fallback
        return str(choices[0].get("text", fallback)).strip() or fallback

    def _llama_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        llama_cls = load_attr("llama_cpp", "Llama")
        if llama_cls is None:
            return None
        self._client = llama_cls(model_path=str(Path(self._model_path).expanduser()))
        return self._client
