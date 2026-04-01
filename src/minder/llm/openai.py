from __future__ import annotations

from minder.graph.state import GraphState


class OpenAIFallbackLLM:
    def __init__(self, api_key: str | None, model: str, runtime: str = "mock") -> None:
        self._api_key = api_key
        self._model = model
        self._runtime = runtime

    def available(self) -> bool:
        return bool(self._api_key)

    def generate(self, state: GraphState) -> dict[str, object]:
        if not self.available():
            raise RuntimeError("OpenAI fallback is not configured")
        text = (
            f"{state.workflow_context.get('guidance', '')}\n"
            f"Fallback answer for '{state.query}' using {self._model}."
        )
        return {
            "text": text,
            "sources": [doc["path"] for doc in state.reranked_docs[:3]],
            "provider": "openai_fallback",
            "model": self._model,
            "runtime": self._runtime,
            "stream": [text],
        }
