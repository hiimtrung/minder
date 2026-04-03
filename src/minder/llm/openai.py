from __future__ import annotations

from typing import Any

from minder.graph.state import GraphState
from minder.runtime import load_attr, module_available


class OpenAIFallbackLLM:
    def __init__(self, api_key: str | None, model: str, runtime: str = "mock") -> None:
        self._api_key = api_key
        self._model = model
        self._runtime = runtime
        self._completion_fn: Any | None = None

    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def runtime(self) -> str:
        if self._runtime == "auto":
            return "litellm" if module_available("litellm") else "mock"
        return self._runtime

    def generate(self, state: GraphState) -> dict[str, object]:
        if not self.available():
            raise RuntimeError("OpenAI fallback is not configured")
        text = (
            f"{state.workflow_context.get('guidance', '')}\n"
            f"Fallback answer for '{state.query}' using {self._model}."
        )
        if self.runtime == "litellm":
            text = self._generate_with_litellm(state, fallback=text)
        return {
            "text": text,
            "sources": [doc["path"] for doc in state.reranked_docs[:3]],
            "provider": "openai_fallback",
            "model": self._model,
            "runtime": self.runtime,
            "stream": [text],
        }

    def _generate_with_litellm(self, state: GraphState, *, fallback: str) -> str:
        completion = self._litellm_completion()
        if completion is None:
            return fallback
        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        try:
            response = completion(
                model=self._model,
                api_key=self._api_key,
                messages=[
                    {
                        "role": "user",
                        "content": str(reasoning_output.get("prompt") or state.query),
                    }
                ],
            )
        except Exception:
            return fallback
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices", [])
        if not choices:
            return fallback
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message", {})
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        return str(content or fallback).strip() or fallback

    def _litellm_completion(self) -> Any | None:
        if self._completion_fn is not None:
            return self._completion_fn
        self._completion_fn = load_attr("litellm", "completion")
        return self._completion_fn
