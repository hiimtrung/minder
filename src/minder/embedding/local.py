"""
Local Embedding provider — delegates to llama-cpp-python using GGUF models.

Falls back to a deterministic hash-based stub if initialization fails.
"""

from __future__ import annotations

import gc
import hashlib
import logging
import math
from collections import OrderedDict
from typing import Any

from minder.runtime import get_writable_hf_cache_dir, llama_cpp_usable

logger = logging.getLogger(__name__)


_MODEL_CACHE: dict[str, Any] = {}
_EMBEDDING_CACHE: OrderedDict[str, list[float]] = OrderedDict()
MAX_CACHE_SIZE = 100
MAX_TEXT_LENGTH = 8000  # Safety truncation to avoid over-context (~2000 tokens)


class LocalEmbeddingProvider:
    def __init__(
        self,
        llama_cpp_model_repo: str = "ggml-org/embeddinggemma-300M-GGUF",
        llama_cpp_model_file: str = "*Q4_K_M.gguf",
        dimensions: int = 768,
        runtime: str = "auto",
    ) -> None:
        self._model_repo = llama_cpp_model_repo
        self._model_file = llama_cpp_model_file
        self._dimensions = dimensions
        self._runtime = runtime
        self._model: Any | None = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._init_model()
            self._initialized = True

    def _init_model(self) -> None:
        if self._runtime == "mock":
            return

        cache_key = f"{self._model_repo}:{self._model_file}"
        if cache_key in _MODEL_CACHE:
            self._model = _MODEL_CACHE[cache_key]
            return

        if not llama_cpp_usable():
            logger.warning("llama.cpp not usable on this host; embedding running in mock mode.")
            return

        try:
            from llama_cpp import Llama

            logger.info("Initializing Llama.cpp embedding engine for %s", self._model_repo)
            cache_dir = get_writable_hf_cache_dir()
            cache_kwargs: dict[str, Any] = (
                {} if cache_dir is None else {"cache_dir": cache_dir}
            )
            self._model = Llama.from_pretrained(
                repo_id=self._model_repo,
                filename=self._model_file,
                embedding=True,
                verbose=False,
                **cache_kwargs,
            )
            _MODEL_CACHE[cache_key] = self._model
        except Exception as e:
            logger.warning(
                "Failed to initialize Llama.cpp model %s: %s. Using mock.",
                self._model_repo, e,
            )
            self._model = None

    @property
    def runtime(self) -> str:
        if self._runtime != "auto":
            return self._runtime
        return "llama_cpp" if self._model is not None else "mock"

    def embed(self, text: str) -> list[float]:
        self._ensure_initialized()
        if not text:
            return [0.0] * self._dimensions

        # 1. Truncate to avoid over-context errors
        safe_text = text[:MAX_TEXT_LENGTH]
        
        # 2. Check cache
        if safe_text in _EMBEDDING_CACHE:
            _EMBEDDING_CACHE.move_to_end(safe_text)
            return _EMBEDDING_CACHE[safe_text]

        # 3. Perform embedding
        embedding: list[float]
        if self.runtime == "llama_cpp" and self._model is not None:
            try:
                # llama_cpp returns a dict with 'data'
                result = self._model.create_embedding(safe_text)
                vector = result["data"][0]["embedding"]
                embedding = vector[: self._dimensions]
            except Exception as e:
                logger.warning(f"Llama.cpp failed during embedding inference: {e}")
                embedding = self._hash_embed(safe_text)
        else:
            embedding = self._hash_embed(safe_text)

        # 4. Update cache (LRU)
        _EMBEDDING_CACHE[safe_text] = embedding
        if len(_EMBEDDING_CACHE) > MAX_CACHE_SIZE:
            _EMBEDDING_CACHE.popitem(last=False)

        return embedding

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self._ensure_initialized()
        if not texts:
            return []

        results: list[list[float]] = [[] for _ in texts]
        to_embed_indices: list[int] = []
        to_embed_texts: list[str] = []

        # 1. Try cache first
        for i, text in enumerate(texts):
            safe_text = text[:MAX_TEXT_LENGTH] if text else ""
            if not safe_text:
                results[i] = [0.0] * self._dimensions
            elif safe_text in _EMBEDDING_CACHE:
                _EMBEDDING_CACHE.move_to_end(safe_text)
                results[i] = _EMBEDDING_CACHE[safe_text]
            else:
                to_embed_indices.append(i)
                to_embed_texts.append(safe_text)

        if not to_embed_texts:
            return results

        # 2. Batch embed the missing ones
        if self.runtime == "llama_cpp" and self._model is not None:
            try:
                # pass list of strings directly
                res = self._model.create_embedding(to_embed_texts)
                embeddings = [data["embedding"] for data in res["data"]]
                for i, emb in enumerate(embeddings):
                    idx = to_embed_indices[i]
                    vector = emb[: self._dimensions]
                    results[idx] = vector
                    # Update cache
                    _EMBEDDING_CACHE[to_embed_texts[i]] = vector
            except Exception as e:
                logger.warning(f"Llama.cpp batch embedding failed: {e}")
                for i, idx in enumerate(to_embed_indices):
                    vector = self._hash_embed(to_embed_texts[i])
                    results[idx] = vector
                    _EMBEDDING_CACHE[to_embed_texts[i]] = vector
        else:
            for i, idx in enumerate(to_embed_indices):
                vector = self._hash_embed(to_embed_texts[i])
                results[idx] = vector
                _EMBEDDING_CACHE[to_embed_texts[i]] = vector

        # 3. Cache maintenance
        while len(_EMBEDDING_CACHE) > MAX_CACHE_SIZE:
            _EMBEDDING_CACHE.popitem(last=False)

        return results

    def _hash_embed(self, text: str) -> list[float]:
        """Generate a deterministic but word-aware mock embedding."""
        words = text.lower().split()
        if not words:
            return [0.0] * self._dimensions

        vector = [0.0] * self._dimensions
        for word in words:
            h = hashlib.sha256(word.encode()).digest()
            for i in range(self._dimensions):
                byte_val = h[i % len(h)]
                vector[i] += (byte_val / 255.0) - 0.5

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 1e-9:
            return [v / norm for v in vector]
        return [0.0] * self._dimensions

def clear_caches() -> None:
    """Clear global model and embedding caches to reclaim memory."""
    global _MODEL_CACHE, _EMBEDDING_CACHE
    for model in _MODEL_CACHE.values():
        try:
            if hasattr(model, "close"):
                model.close()
        except Exception:
            pass
    _MODEL_CACHE.clear()
    _EMBEDDING_CACHE.clear()
    gc.collect()
    logger.debug("Cleared Llama.cpp embedding global caches.")
