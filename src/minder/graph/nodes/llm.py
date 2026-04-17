from __future__ import annotations

from collections.abc import Generator

from minder.graph.state import GraphState
from minder.llm.base import LLMClient
from minder.llm.openai import OpenAIFallbackLLM


class LLMNode:
    def __init__(
        self, primary: LLMClient, fallback: OpenAIFallbackLLM | None = None
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def run(self, state: GraphState) -> GraphState:
        try:
            state.llm_output = self._primary.generate(state)
            state.metadata["fallback_used"] = False
            state.metadata["llm_provider"] = state.llm_output.get("provider")
        except Exception as exc:
            state.metadata["llm_error"] = str(exc)
            if self._fallback is None or not self._fallback.available():
                raise
            state.llm_output = self._fallback.generate(state)
            state.metadata["fallback_used"] = True
            state.metadata["llm_provider"] = state.llm_output.get("provider")
        return state

    def stream(self, state: GraphState) -> Generator[dict[str, object], None, None]:
        try:
            streamer = getattr(self._primary, "stream_generate", None)
            if callable(streamer):
                result = None
                for event in streamer(state):
                    if str(event.get("type")) == "result":
                        result = dict(event.get("result", {}) or {})
                        continue
                    yield event
                state.llm_output = result or self._primary.generate(state)
            else:
                state.llm_output = self._primary.generate(state)
                text = str(state.llm_output.get("text", ""))
                if text:
                    yield {"type": "chunk", "delta": text}
            state.metadata["fallback_used"] = False
            state.metadata["llm_provider"] = state.llm_output.get("provider")
        except Exception as exc:
            state.metadata["llm_error"] = str(exc)
            if self._fallback is None or not self._fallback.available():
                raise
            state.llm_output = self._fallback.generate(state)
            text = str(state.llm_output.get("text", ""))
            if text:
                yield {"type": "chunk", "delta": text}
            state.metadata["fallback_used"] = True
            state.metadata["llm_provider"] = state.llm_output.get("provider")
        yield {"type": "result", "result": state.llm_output}
