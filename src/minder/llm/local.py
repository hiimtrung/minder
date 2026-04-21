"""
Local LLM provider — delegates inference to an Ollama HTTP server.

Ollama must be running and accessible at the configured URL (default
``http://localhost:11434``).  The provider gracefully falls back to a
deterministic text stub when Ollama is unreachable so that the rest of
the Minder pipeline can still operate.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from minder.graph.state import GraphState

logger = logging.getLogger(__name__)


class LocalModelLLM:

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "gemma3:4b",
        fail: bool = False,
        context_length: int = 131072,
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._ollama_model = ollama_model
        self._fail = fail
        self._context_length = max(512, context_length)

    @property
    def runtime(self) -> str:
        if self._fail:
            return "mock"
        try:
            req = Request(f"{self._ollama_url}/api/tags", method="GET")
            with urlopen(req, timeout=3):
                return "ollama"
        except Exception:
            return "mock"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, state: GraphState) -> dict[str, object]:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        runtime = self.runtime
        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        fallback = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )

        text = fallback
        if runtime == "ollama":
            text = self._generate_with_ollama(state, fallback=fallback)

        return {
            "text": text,
            "sources": source_paths,
            "provider": "local_llm",
            "model": self._ollama_model,
            "runtime": runtime,
            "stream": [line for line in text.splitlines() if line],
        }

    def stream_generate(
        self, state: GraphState
    ) -> Generator[dict[str, object], None, None]:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        runtime = self.runtime
        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        fallback = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )

        if runtime != "ollama":
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": self._build_result(fallback, source_paths, runtime),
            }
            return

        deltas: list[str] = []
        try:
            for delta in self._stream_ollama(str(state.query)):
                deltas.append(delta)
                yield {"type": "chunk", "delta": delta}
        except Exception:
            logger.warning("Ollama stream failed, using fallback")
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            deltas = [fallback] if fallback else []

        text = "".join(deltas).strip() or fallback
        yield {
            "type": "result",
            "result": self._build_result(text, source_paths, runtime, deltas),
        }

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        fallback: str = "",
    ) -> str:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        if self.runtime != "ollama":
            return fallback

        try:
            return self._chat_ollama(prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception:
            logger.warning("Ollama completion failed, using fallback")
            return fallback

    # ------------------------------------------------------------------
    # Ollama HTTP helpers
    # ------------------------------------------------------------------

    def _chat_ollama(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        payload = {
            "model": self._ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._context_length,
            },
        }
        data = json.dumps(payload).encode()
        req = Request(
            f"{self._ollama_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
        return body.get("message", {}).get("content", "").strip()

    def _stream_ollama(
        self,
        prompt: str,
        *,
        max_tokens: int = 256,
        temperature: float = 0.1,
    ) -> Generator[str, None, None]:
        payload = {
            "model": self._ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._context_length,
            },
        }
        data = json.dumps(payload).encode()
        req = Request(
            f"{self._ollama_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            for line in resp:
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

    def _generate_with_ollama(self, state: GraphState, *, fallback: str) -> str:
        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        prompt = reasoning_output.get("prompt") or state.query
        return self.complete_text(
            str(prompt),
            max_tokens=256,
            temperature=0.1,
            fallback=fallback,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_result(
        self,
        text: str,
        source_paths: list[str],
        runtime: str,
        stream: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "text": text,
            "sources": source_paths,
            "provider": "local_llm",
            "model": self._ollama_model,
            "runtime": runtime,
            "stream": stream if stream else ([text] if text else []),
        }
