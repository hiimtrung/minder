"""
Local Embedding provider — delegates to FastEmbed using ONNX runtime.

Falls back to a deterministic hash-based stub if initialization fails.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_MODEL_CACHE: dict[str, Any] = {}
_EMBEDDING_CACHE: OrderedDict[str, list[float]] = OrderedDict()
MAX_CACHE_SIZE = 1000
MAX_TEXT_LENGTH = 8000  # Safety truncation to avoid over-context (~2000 tokens)


class LocalEmbeddingProvider:
    def __init__(
        self,
        fastembed_model: str = "mixedbread-ai/mxbai-embed-large-v1",
        fastembed_cache_dir: str = "~/.minder/cache/fastembed",
        dimensions: int = 1024,
        runtime: str = "auto",
    ) -> None:
        self._model_name = fastembed_model
        self._cache_dir = str(Path(fastembed_cache_dir).expanduser())
        self._dimensions = dimensions
        self._runtime = runtime
        self._model: Any | None = None
        self._init_model()

    def _init_model(self) -> None:
        if self._runtime == "mock":
            return

        cache_key = f"{self._model_name}:{self._cache_dir}"
        if cache_key in _MODEL_CACHE:
            self._model = _MODEL_CACHE[cache_key]
            return

        try:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]

            # Optimize for speed and resource usage:
            # - threads=4 limits CPU usage while maintaining good throughput
            # - lazy_load=False ensures first request is fast
            self._model = TextEmbedding(
                model_name=self._model_name,
                cache_dir=self._cache_dir,
                threads=4,
            )
            _MODEL_CACHE[cache_key] = self._model
        except Exception as e:
            logger.warning(
                f"Failed to initialize FastEmbed model {self._model_name}: {e}. Using mock."
            )
            self._model = None

    @property
    def runtime(self) -> str:
        if self._runtime != "auto":
            return self._runtime
        return "fastembed" if self._model is not None else "mock"

    def embed(self, text: str) -> list[float]:
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
        if self.runtime == "fastembed" and self._model is not None:
            try:
                # FastEmbed returns a generator of numpy arrays
                embeddings = list(self._model.embed([safe_text]))
                if embeddings:
                    embedding = embeddings[0].tolist()[: self._dimensions]
                else:
                    embedding = self._hash_embed(safe_text)
            except Exception as e:
                logger.warning(f"FastEmbed failed during inference: {e}")
                embedding = self._hash_embed(safe_text)
        else:
            embedding = self._hash_embed(safe_text)

        # 4. Update cache (LRU)
        _EMBEDDING_CACHE[safe_text] = embedding
        if len(_EMBEDDING_CACHE) > MAX_CACHE_SIZE:
            _EMBEDDING_CACHE.popitem(last=False)

        return embedding

    def embed_many(self, texts: list[str]) -> list[list[float]]:
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
        if self.runtime == "fastembed" and self._model is not None:
            try:
                embeddings = list(self._model.embed(to_embed_texts))
                for i, emb in enumerate(embeddings):
                    idx = to_embed_indices[i]
                    vector = emb.tolist()[: self._dimensions]
                    results[idx] = vector
                    # Update cache
                    _EMBEDDING_CACHE[to_embed_texts[i]] = vector
            except Exception as e:
                logger.warning(f"FastEmbed batch failed: {e}")
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
