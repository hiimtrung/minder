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
        # Strip the large prompt/messages fields — they are only needed by the LLM
        # and keeping them inflates state size for every subsequent node
        # (especially costly in LangGraph which serializes state at each boundary).
        self._strip_inference_artifacts(state)
        return state

    async def arun(self, state: GraphState) -> GraphState:
        """Async LLM node: streams tokens via LangGraph custom events for astream_events()."""
        from langchain_core.callbacks.manager import adispatch_custom_event

        from minder.graph.concurrency import stream_sync_generator

        try:
            streamer = getattr(self._primary, "stream_generate", None)
            if callable(streamer):
                result = None
                async for event in stream_sync_generator(streamer, state, use_llm_semaphore=True):
                    if str(event.get("type")) == "result":
                        result = dict(event.get("result", {}) or {})
                    elif str(event.get("type")) == "chunk":
                        delta = str(event.get("delta", ""))
                        if delta:
                            await adispatch_custom_event("llm_token", {"delta": delta})
                state.llm_output = result or self._primary.generate(state)
            else:
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
        # Strip large prompt/messages — only needed during inference, not by downstream nodes.
        self._strip_inference_artifacts(state)
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
        # Strip large prompt/messages before yielding final result.
        self._strip_inference_artifacts(state)
        yield {"type": "result", "result": state.llm_output}

    @staticmethod
    def _strip_inference_artifacts(state: GraphState) -> None:
        """Remove large fields from reasoning_output that are only needed during inference.

        ``prompt`` and ``messages`` can be 10-100 KB each.  Keeping them in
        state inflates every subsequent node's serialized payload — especially
        harmful in LangGraph which serializes at every node boundary.
        """
        ro = state.reasoning_output
        if ro and isinstance(ro, dict):
            ro.pop("prompt", None)
            ro.pop("messages", None)
