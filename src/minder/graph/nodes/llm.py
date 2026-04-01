from __future__ import annotations

from minder.graph.state import GraphState
from minder.llm.base import LLMClient
from minder.llm.openai import OpenAIFallbackLLM


class LLMNode:
    def __init__(self, primary: LLMClient, fallback: OpenAIFallbackLLM | None = None) -> None:
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
