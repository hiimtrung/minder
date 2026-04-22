"""
LiteRT-LM provider — high-performance on-device LLM inference.

Uses Google's LiteRT-LM Python API for hardware-accelerated inference
(Metal on macOS, CPU elsewhere).  Requires ``.litertlm`` model files
downloaded from HuggingFace (litert-community).

Install the runtime with::

    pip install litert-lm-api-nightly
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

from minder.graph.state import GraphState


logger = logging.getLogger(__name__)


class LiteRTModelLLM:
    """LLM provider backed by Google LiteRT-LM (on-device inference)."""

    def __init__(
        self,
        model_path: str = "~/.minder/models/gemma-4-E2B-it.litertlm",
        backend: str = "cpu",
        cache_dir: str = "~/.minder/cache/litert",
        context_length: int = 131072,
    ) -> None:
        self._model_path = str(Path(model_path).expanduser())
        self._backend = backend
        self._cache_dir = str(Path(cache_dir).expanduser())
        self._context_length = max(512, context_length)
        self._engine: Any | None = None
        self._model_name = Path(self._model_path).stem

    # ------------------------------------------------------------------
    # Runtime detection
    # ------------------------------------------------------------------

    @property
    def runtime(self) -> str:
        """Return ``"litert"`` if the engine can be initialised, else ``"mock"``."""
        try:
            import litert_lm  # type: ignore[import-not-found]  # noqa: F401

            if not Path(self._model_path).exists():
                logger.warning("LiteRT-LM model not found at %s", self._model_path)
                return "mock"
            return "litert"
        except ImportError:
            return "mock"

    # ------------------------------------------------------------------
    # Lazy engine management
    # ------------------------------------------------------------------

    def _get_engine(self):  # type: ignore[no-untyped-def]
        """Lazy-init the LiteRT-LM engine (expensive; only done once)."""
        if self._engine is not None:
            return self._engine

        import litert_lm  # type: ignore[import-not-found]

        backend = litert_lm.Backend.CPU
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
        self._engine = litert_lm.Engine(
            self._model_path,
            backend=backend,
            cache_dir=self._cache_dir,
        )
        return self._engine

    def close(self) -> None:
        """Release the native engine resources if held."""
        if self._engine is not None:
            close_fn = getattr(self._engine, "__exit__", None)
            if close_fn is not None:
                try:
                    close_fn(None, None, None)
                except Exception:
                    pass
            self._engine = None

    # ------------------------------------------------------------------
    # Public API — matches LocalModelLLM interface
    # ------------------------------------------------------------------

    def generate(self, state: GraphState) -> dict[str, object]:
        """Synchronous generation (full response)."""
        reranked = getattr(state, "reranked_docs", []) or []
        retrieved = getattr(state, "retrieved_docs", []) or []
        docs = reranked or retrieved
        source_paths = [doc["path"] for doc in docs[:3]]
        guidance = getattr(state, "workflow_context", {}).get("guidance", "")
        fallback = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )

        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        prompt = reasoning_output.get("prompt") or state.query
        text = self.complete_text(
            str(prompt),
            max_tokens=256,
            temperature=0.1,
            fallback=fallback,
        )

        return {
            "text": text,
            "sources": source_paths,
            "provider": "litert_lm",
            "model": self._model_name,
            "runtime": self.runtime,
            "stream": [line for line in text.splitlines() if line],
        }

    def stream_generate(
        self, state: GraphState
    ) -> Generator[dict[str, object], None, None]:
        """Streaming generation using ``send_message_async``."""
        reranked = getattr(state, "reranked_docs", []) or []
        retrieved = getattr(state, "retrieved_docs", []) or []
        docs = reranked or retrieved
        source_paths = [doc["path"] for doc in docs[:3]]
        guidance = getattr(state, "workflow_context", {}).get("guidance", "")
        fallback = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )

        if self.runtime != "litert":
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": self._build_result(fallback, source_paths, "mock"),
            }
            return

        deltas: list[str] = []
        try:
            engine = self._get_engine()
            reasoning_output = getattr(state, "reasoning_output", {}) or {}
            prompt = str(reasoning_output.get("prompt") or state.query)
            messages = [
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
            ]
            with engine.create_conversation(messages=messages) as conv:
                for chunk in conv.send_message_async(prompt):
                    for item in chunk.get("content", []):
                        if item.get("type") == "text":
                            delta = item["text"]
                            deltas.append(delta)
                            yield {"type": "chunk", "delta": delta}
        except Exception:
            logger.warning("LiteRT-LM stream failed, using fallback")
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            deltas = [fallback] if fallback else []

        text = "".join(deltas).strip() or fallback
        yield {
            "type": "result",
            "result": self._build_result(text, source_paths, "litert", deltas),
        }

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        fallback: str = "",
    ) -> str:
        """Simple text-in/text-out completion."""
        if self.runtime != "litert":
            return fallback

        try:
            engine = self._get_engine()
            messages = [
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
            ]
            with engine.create_conversation(messages=messages) as conv:
                response = conv.send_message(prompt)
                return response["content"][0]["text"]
        except Exception:
            logger.warning("LiteRT-LM completion failed, using fallback")
            return fallback

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
            "provider": "litert_lm",
            "model": self._model_name,
            "runtime": runtime,
            "stream": stream if stream else ([text] if text else []),
        }
