"""
LiteRT-LM provider — high-performance on-device LLM inference.

Uses Google's LiteRT-LM Python API for hardware-accelerated inference
(Metal on macOS, CPU elsewhere).  Requires ``.litertlm`` model files
downloaded from HuggingFace (litert-community).

Install the runtime with::

    pip install litert-lm-api-nightly
"""

from __future__ import annotations
import gc
import logging
import platform
import uuid
from collections import OrderedDict
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

from minder.graph.state import GraphState


logger = logging.getLogger(__name__)


_ENGINE_CACHE: dict[str, Any] = {}
_CONVERSATION_CACHE: OrderedDict[uuid.UUID, Any] = OrderedDict()
MAX_CACHED_CONVERSATIONS = 3


class LiteRTModelLLM:
    """LLM provider backed by Google LiteRT-LM (on-device inference)."""

    def __init__(
        self,
        model_path: str = "~/.minder/models/gemma-4-E2B-it.litertlm",
        backend: str = "cpu",
        cache_dir: str = "~/.minder/cache/litert",
        context_length: int = 32768,
    ) -> None:
        self._model_path = str(Path(model_path).expanduser())
        self._backend = backend
        self._cache_dir = str(Path(cache_dir).expanduser())
        self._context_length = max(512, context_length)
        self._engine: Any | None = None
        self._model_name = Path(self._model_path).stem
        if self._backend != "mock":
            self._init_engine()

    def _init_engine(self) -> None:
        """Initialize the LiteRT engine with the requested backend."""
        if self._backend == "mock":
            return

        cache_key = f"{self._model_path}:{self._backend}"
        if cache_key in _ENGINE_CACHE:
            self._engine = _ENGINE_CACHE[cache_key]
            return

        try:
            import litert_lm  # type: ignore[import-untyped]
            
            # Map string backend to LiteRT-LM enum with platform-aware defaults
            backend_str = self._backend.lower()
            system = platform.system()

            if backend_str == "gpu":
                backend = litert_lm.Backend.GPU
            elif backend_str == "cpu":
                backend = litert_lm.Backend.CPU
            elif backend_str == "auto":
                if system == "Darwin":
                    backend = litert_lm.Backend.GPU
                elif system == "Linux":
                    backend = litert_lm.Backend.CPU
                else:
                    backend = litert_lm.Backend.UNSPECIFIED
            else:
                backend = litert_lm.Backend.UNSPECIFIED

            Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
            self._engine = litert_lm.Engine(
                self._model_path,
                backend=backend,
                cache_dir=self._cache_dir,
                max_num_tokens=self._context_length,
            )
            _ENGINE_CACHE[cache_key] = self._engine
        except Exception as e:
            logger.warning("Failed to initialize LiteRT engine: %s. Falling back to mock mode.", e)
            self._backend = "mock"

    # ------------------------------------------------------------------
    # Runtime detection
    # ------------------------------------------------------------------

    @property
    def runtime(self) -> str:
        """Return ``"litert"`` if the engine can be initialised, else ``"mock"``."""
        if self._backend == "mock":
            return "mock"
        try:
            import litert_lm  # type: ignore[import-not-found, import-untyped]  # noqa: F401

            if not Path(self._model_path).exists():
                logger.warning("LiteRT-LM model not found at %s", self._model_path)
                return "mock"
            return "litert"
        except ImportError:
            return "mock"

    # ------------------------------------------------------------------
    # Lazy engine management
    # ------------------------------------------------------------------

    def _get_engine(self) -> Any:
        """Lazy-init the LiteRT-LM engine (expensive; only done once)."""
        if self._engine is None and self._backend != "mock":
            self._init_engine()
        return self._engine

    def _get_conversation(self, session_id: uuid.UUID | None, initial_messages: list[dict[str, Any]]) -> Any:
        """Get or create a conversation for the session (enables KV-cache reuse)."""
        if session_id is None:
            engine = self._get_engine()
            return engine.create_conversation(messages=initial_messages)

        if session_id in _CONVERSATION_CACHE:
            # Move to end (LRU)
            _CONVERSATION_CACHE.move_to_end(session_id)
            return _CONVERSATION_CACHE[session_id]

        # Purge oldest if limit reached
        if len(_CONVERSATION_CACHE) >= MAX_CACHED_CONVERSATIONS:
            oldest_id, oldest_conv = _CONVERSATION_CACHE.popitem(last=False)
            try:
                # Explicitly close conversation resources
                if hasattr(oldest_conv, "__exit__"):
                    oldest_conv.__exit__(None, None, None)
            except Exception:
                pass
            logger.debug("Purged old LiteRT-LM conversation session: %s", oldest_id)

        engine = self._get_engine()
        conv = engine.create_conversation(messages=initial_messages)
        _CONVERSATION_CACHE[session_id] = conv
        return conv

    def close(self) -> None:
        """Release the native engine resources and all active conversations."""
        # Clean up all cached conversations first
        while _CONVERSATION_CACHE:
            _, conv = _CONVERSATION_CACHE.popitem()
            try:
                if hasattr(conv, "__exit__"):
                    conv.__exit__(None, None, None)
            except Exception:
                pass

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
        chat_history = getattr(state, "chat_history", []) or []
        text = self.complete_text(
            str(prompt),
            max_tokens=256,
            temperature=0.1,
            fallback=fallback,
            session_id=state.session_id,
            chat_history=chat_history,
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
            reasoning_output = getattr(state, "reasoning_output", {}) or {}
            prompt = str(reasoning_output.get("prompt") or state.query)
            chat_history = getattr(state, "chat_history", []) or []
            
            # Use session cache if available. Reusing the conversation preserves the KV-cache state.
            # For linear conversations, we don't pass 'messages' to send_message_async because
            # it builds on top of the existing state in the Conversation object.
            conv = self._get_conversation(state.session_id, initial_messages=chat_history)
            
            for chunk in conv.send_message_async(prompt):
                for item in chunk.get("content", []):
                    if item.get("type") == "text":
                        delta = item["text"]
                        deltas.append(delta)
                        yield {"type": "chunk", "delta": delta}
        except Exception as e:
            logger.warning("LiteRT-LM stream failed: %s", e)
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
        session_id: uuid.UUID | None = None,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Simple text-in/text-out completion."""
        if self.runtime != "litert":
            return fallback

        try:
            conv = self._get_conversation(session_id, initial_messages=chat_history or [])
            response = conv.send_message(prompt)
            return cast(str, response["content"][0]["text"])
        except Exception as e:
            logger.warning("LiteRT-LM completion failed: %s", e)
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

def clear_caches() -> None:
    """Clear global engine and conversation caches to reclaim memory."""
    global _ENGINE_CACHE, _CONVERSATION_CACHE
    
    # Try to close conversations
    for conv in _CONVERSATION_CACHE.values():
        try:
            if hasattr(conv, "__exit__"):
                conv.__exit__(None, None, None)
        except Exception:
            pass
    
    _CONVERSATION_CACHE.clear()
    
    # Engines are harder to close explicitly in current API, but we drop references
    _ENGINE_CACHE.clear()
    gc.collect()
    logger.debug("Cleared LiteRT-LM global caches.")
