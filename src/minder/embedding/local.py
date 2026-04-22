"""
Local Embedding provider — delegates to FastEmbed using ONNX runtime.

Falls back to a deterministic hash-based stub if initialization fails.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_MODEL_CACHE: dict[str, Any] = {}


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

            self._model = TextEmbedding(
                model_name=self._model_name,
                cache_dir=self._cache_dir,
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
        if self.runtime == "fastembed" and self._model is not None:
            try:
                # FastEmbed returns a generator of numpy arrays
                embeddings = list(self._model.embed([text]))
                if embeddings and len(embeddings) > 0:
                    return embeddings[0].tolist()[: self._dimensions]
            except Exception as e:
                logger.warning(f"FastEmbed failed during inference: {e}")

        # Deterministic hash-based fallback
        return self._hash_embed(text)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.runtime == "fastembed" and self._model is not None:
            try:
                # FastEmbed returns a generator of numpy arrays
                embeddings = list(self._model.embed(texts))
                return [
                    emb.tolist()[: self._dimensions] for emb in embeddings
                ]
            except Exception as e:
                logger.warning(f"FastEmbed batch failed during inference: {e}")

        return [self._hash_embed(text) for text in texts]

    def _hash_embed(self, text: str) -> list[float]:
        # Deterministic hash-based fallback
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for index in range(self._dimensions):
            byte = digest[index % len(digest)]
            values.append(round(byte / 255.0, 6))
        return values
