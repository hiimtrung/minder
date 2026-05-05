"""
Llama.cpp provider — high-performance local LLM inference.

Uses `llama-cpp-python` for hardware-accelerated inference.
Automatically downloads models from Hugging Face Hub if they don't exist locally.
"""

from __future__ import annotations
import gc
import logging
from collections.abc import Generator
from typing import Any, cast

from minder.graph.state import GraphState
from minder.runtime import llama_cpp_usable

logger = logging.getLogger(__name__)


_ENGINE_CACHE: dict[str, Any] = {}
# ~3 chars per token; truncate at 90% of context_length to leave room for output
_CHARS_PER_TOKEN = 3


class LlamaCppLLM:
    """LLM provider backed by llama-cpp-python (GGUF inference)."""

    def __init__(
        self,
        model_repo: str = "ggml-org/gemma-4-E2B-it-GGUF",
        model_file: str = "*.gguf",
        context_length: int = 16384,
        temperature: float = 0.1,
        runtime: str = "auto",
    ) -> None:
        self._model_repo = model_repo
        self._model_file = model_file
        self._context_length = max(512, context_length)
        self._temperature = temperature
        self._runtime_override = runtime
        self._engine: Any = None  # None until initialized; Llama instance after _init_engine
        self._model_name = self._model_repo.split("/")[-1]
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._init_engine()
            self._initialized = True

    def _init_engine(self) -> None:
        if self._runtime_override == "mock":
            return

        if not llama_cpp_usable():
            logger.warning(
                "CPU does not support AVX2; llama.cpp unavailable. Falling back to mock mode."
            )
            return

        cache_key = f"{self._model_repo}:{self._model_file}"
        if cache_key in _ENGINE_CACHE:
            self._engine = _ENGINE_CACHE[cache_key]
            return

        try:
            from llama_cpp import Llama

            n_gpu_layers = -1  # Let llama.cpp handle Metal / CUDA layer offloading
            logger.info("Initializing Llama.cpp engine for %s", self._model_repo)
            self._engine = Llama.from_pretrained(
                repo_id=self._model_repo,
                filename=self._model_file,
                n_ctx=self._context_length,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            _ENGINE_CACHE[cache_key] = self._engine
        except Exception as e:
            logger.warning("Failed to initialize Llama.cpp engine: %s. Falling back to mock mode.", e)
            self._engine = None

    # ------------------------------------------------------------------
    # Runtime detection
    # ------------------------------------------------------------------

    @property
    def runtime(self) -> str:
        """Return ``"llama_cpp"`` if the engine can be initialised, else ``"mock"``."""
        if self._runtime_override != "auto":
            return self._runtime_override
        if self._engine is None:
            return "mock"
        return "llama_cpp"

    def close(self) -> None:
        """Release the native engine resources."""
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, state: GraphState) -> dict[str, object]:
        self._ensure_initialized()
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
            temperature=self._temperature,
            fallback=fallback,
        )

        return {
            "text": text,
            "sources": source_paths,
            "provider": "llama_cpp",
            "model": self._model_name,
            "runtime": self.runtime,
            "stream": [line for line in text.splitlines() if line],
        }

    def stream_generate(
        self, state: GraphState
    ) -> Generator[dict[str, object], None, None]:
        self._ensure_initialized()
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

        if self.runtime != "llama_cpp":
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": self._build_result(fallback, source_paths, "mock"),
            }
            return

        deltas: list[str] = []
        try:
            reasoning_output = getattr(state, "reasoning_output", {}) or {}
            prompt = self._truncate_prompt(str(reasoning_output.get("prompt") or state.query))

            response = self._engine(
                prompt,
                max_tokens=2048,
                temperature=self._temperature,
                stream=True,
            )

            for chunk in response:
                delta = chunk["choices"][0]["text"]
                if delta:
                    deltas.append(delta)
                    yield {"type": "chunk", "delta": delta}
        except Exception as e:
            logger.warning("Llama.cpp stream failed: %s", e)
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            deltas = [fallback] if fallback else []

        text = "".join(deltas).strip() or fallback
        yield {
            "type": "result",
            "result": self._build_result(text, source_paths, "llama_cpp", deltas),
        }

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        fallback: str = "",
    ) -> str:
        self._ensure_initialized()
        if self.runtime != "llama_cpp":
            return fallback

        try:
            response = self._engine(
                self._truncate_prompt(prompt),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
            return cast(str, response["choices"][0]["text"])
        except Exception as e:
            logger.warning("Llama.cpp completion failed: %s", e)
            return fallback

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _truncate_prompt(self, prompt: str) -> str:
        """Truncate prompt to fit within context_length."""
        max_chars = int(self._context_length * 0.9) * _CHARS_PER_TOKEN
        if len(prompt) <= max_chars:
            return prompt
        logger.warning(
            "Prompt truncated from %d to %d chars to fit context_length=%d",
            len(prompt), max_chars, self._context_length,
        )
        return prompt[-max_chars:]

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
            "provider": "llama_cpp",
            "model": self._model_name,
            "runtime": runtime,
            "stream": stream if stream else ([text] if text else []),
        }

def clear_caches() -> None:
    """Clear global engine caches to reclaim memory."""
    global _ENGINE_CACHE
    for engine in _ENGINE_CACHE.values():
        try:
            if hasattr(engine, "close"):
                engine.close()
        except Exception:
            pass
    _ENGINE_CACHE.clear()
    gc.collect()
    logger.debug("Cleared Llama.cpp global caches.")
