"""
Llama.cpp provider — high-performance local LLM inference.

Uses `llama-cpp-python` for hardware-accelerated inference.
Automatically downloads models from Hugging Face Hub if they don't exist locally.
"""

from __future__ import annotations
import gc
import logging
import re as _re
from collections.abc import Generator
from typing import Any, cast

from minder.graph.state import GraphState
from minder.infrastructure.runtime import get_writable_hf_cache_dir, llama_cpp_usable

logger = logging.getLogger(__name__)


_ENGINE_CACHE: dict[str, Any] = {}
# cache_key → error string from the last failed _init_engine() call.
# Exposed so the status API can surface a real error reason instead of "mock".
_INIT_ERRORS: dict[str, str] = {}
# ~3 chars per token; truncate at 90% of context_length to leave room for output
_CHARS_PER_TOKEN = 3
_THINK_RE = _re.compile(r"<think>.*?</think>", _re.DOTALL)


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
        import os
        self._runtime_override = os.environ.get("MINDER_LLM__RUNTIME") or runtime
        self._engine: Any = None  # None until initialized; Llama instance after _init_engine
        self._model_name = self._model_repo.split("/")[-1]
        self._initialized = False
        self._init_error: str | None = None  # Set when _init_engine() fails
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._init_engine()
            self._initialized = True

    def _init_engine(self) -> None:
        if self._runtime_override == "mock":
            return

        if not llama_cpp_usable():
            logger.warning("llama.cpp not usable on this host; LLM running in mock mode.")
            return

        from minder.infrastructure.hardware import get_hardware_profile

        hw = get_hardware_profile(max_ctx=self._context_length)

        # Cache key incorporates actual hardware-derived settings so two
        # instances with the same model but different HW profiles get the right
        # engine, and so that changing settings invalidates the cache.
        cache_key = (
            f"{self._model_repo}:{self._model_file}"
            f":ctx{hw.n_ctx}:batch{hw.n_batch}"
        )
        if cache_key in _ENGINE_CACHE:
            self._engine = _ENGINE_CACHE[cache_key]
            return

        try:
            from llama_cpp import Llama

            logger.info(
                "Initializing Llama.cpp engine for %s "
                "[n_ctx=%d n_batch=%d n_ubatch=%d n_gpu_layers=%d flash_attn=%s ram=%.0fGB]",
                self._model_repo,
                hw.n_ctx, hw.n_batch, hw.n_ubatch, hw.n_gpu_layers,
                hw.use_flash_attn, hw.total_ram_gb,
            )

            init_kwargs: dict[str, Any] = {
                "n_ctx": hw.n_ctx,
                "n_gpu_layers": hw.n_gpu_layers,
                "n_batch": hw.n_batch,
                "flash_attn": hw.use_flash_attn,
                "verbose": False,
            }
            # n_ubatch reduces Metal scratch-buffer allocation; only pass when
            # the installed llama-cpp-python version supports it.
            if hw.n_ubatch > 0:
                try:
                    import inspect
                    from llama_cpp import Llama as _LlamaInspect
                    if "n_ubatch" in inspect.signature(_LlamaInspect.__init__).parameters:
                        init_kwargs["n_ubatch"] = hw.n_ubatch
                except Exception:
                    pass
            if hw.n_threads > 0:
                init_kwargs["n_threads"] = hw.n_threads

            cache_dir = get_writable_hf_cache_dir()
            cache_kwargs: dict[str, Any] = (
                {} if cache_dir is None else {"cache_dir": cache_dir}
            )
            self._engine = Llama.from_pretrained(
                repo_id=self._model_repo,
                filename=self._model_file,
                **init_kwargs,
                **cache_kwargs,
            )
            # Store the effective context length so truncation uses the real value.
            self._context_length = hw.n_ctx
            _ENGINE_CACHE[cache_key] = self._engine
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Llama.cpp engine failed to initialize for %s/%s: %s",
                self._model_repo, self._model_file, error_msg,
                exc_info=True,
            )
            self._engine = None
            self._init_error = error_msg
            _INIT_ERRORS[cache_key] = error_msg

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
        fallback = self._build_mock_response(state, source_paths)

        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        messages = reasoning_output.get("messages") or []

        if messages and self.runtime == "llama_cpp" and self._engine is not None:
            try:
                response = self._engine.create_chat_completion(
                    messages,
                    max_tokens=512,
                    temperature=self._temperature,
                    stream=False,
                )
                text = self._strip_thinking(str(response["choices"][0]["message"].get("content", "")))
                # If the model produced a useless placeholder, retry with a minimal prompt.
                if not text or text.upper() in ("N/A", "NA", "NONE", "-"):
                    minimal = [
                        {"role": "system", "content": "You are a helpful assistant. Answer briefly."},
                        {"role": "user", "content": state.query},
                    ]
                    resp2 = self._engine.create_chat_completion(
                        minimal, max_tokens=512, temperature=0.3, stream=False
                    )
                    text = self._strip_thinking(str(resp2["choices"][0]["message"].get("content", ""))) or fallback
            except Exception as e:
                logger.warning("create_chat_completion failed, falling back to text: %s", e)
                prompt = reasoning_output.get("prompt") or state.query
                text = self.complete_text(str(prompt), max_tokens=1024, temperature=self._temperature, fallback=fallback)
        else:
            prompt = reasoning_output.get("prompt") or state.query
            text = self.complete_text(str(prompt), max_tokens=1024, temperature=self._temperature, fallback=fallback)

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
        fallback = self._build_mock_response(state, source_paths)

        if self.runtime != "llama_cpp":
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": self._build_result(fallback, source_paths, "mock"),
            }
            return

        deltas: list[str] = []
        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        messages = reasoning_output.get("messages") or []

        try:
            if messages:
                response = self._engine.create_chat_completion(
                    messages,
                    max_tokens=512,
                    temperature=self._temperature,
                    stream=True,
                )
                for chunk in response:
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        deltas.append(delta)
                        yield {"type": "chunk", "delta": delta}
            else:
                prompt = self._truncate_prompt(
                    str(reasoning_output.get("prompt") or state.query)
                )
                response = self._engine(
                    prompt,
                    max_tokens=512,
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

        text = self._strip_thinking("".join(deltas)) or fallback
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
            return self._strip_thinking(cast(str, response["choices"][0]["text"]))
        except Exception as e:
            logger.warning("Llama.cpp completion failed: %s", e)
            return fallback

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove Qwen3-style <think>...</think> blocks from output."""
        return _THINK_RE.sub("", text).strip()

    def _truncate_prompt(self, prompt: str) -> str:
        """Truncate prompt to fit within context_length, preserving head and tail."""
        max_chars = int(self._context_length * 0.9) * _CHARS_PER_TOKEN
        if len(prompt) <= max_chars:
            return prompt
        logger.warning(
            "Prompt truncated from %d to %d chars to fit context_length=%d",
            len(prompt),
            max_chars,
            self._context_length,
        )
        # Keep the first 25% (system/workflow instructions) and last 75% (recent context + question).
        head = max_chars // 4
        tail = max_chars - head
        return prompt[:head] + "\n[...context truncated...]\n" + prompt[-tail:]

    def _build_mock_response(self, state: GraphState, source_paths: list[str]) -> str:
        """Build an honest response when the LLM engine is not available.

        Always explains the actual reason rather than returning fake content.
        """
        intent = str((state.plan or {}).get("intent", "unknown"))

        if self._init_error:
            # Engine tried to load but failed — report the actual error.
            short_err = self._init_error[:300]
            if intent == "chat":
                return (
                    f"I'm Minder, but the local LLM engine failed to start: {short_err}. "
                    "Check the server logs for details."
                )
            return f"LLM engine error: {short_err}"

        if self._runtime_override == "mock":
            # Explicitly configured as mock — this is intentional test mode.
            if intent == "chat":
                return "Hello! I'm Minder (running in mock mode)."
            return f"[mock mode] No real LLM response for: {state.query}"

        # Engine never loaded (likely still downloading or llama.cpp unavailable).
        if intent == "chat":
            return (
                "I'm Minder. The local LLM is still loading — "
                "please wait a moment and try again."
            )
        if source_paths:
            paths_summary = ", ".join(source_paths[:3])
            return (
                f"LLM is loading. Retrieved {len(source_paths)} source(s): {paths_summary}. "
                "Please retry once the model finishes loading."
            )
        return (
            "LLM is loading or unavailable. "
            "Please ensure the model file is downloaded and try again."
        )

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
