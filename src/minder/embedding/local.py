"""
Local Embedding provider — delegates to Ollama HTTP API.

Falls back to a deterministic hash-based stub when Ollama is unreachable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3-embedding:0.6b",
        dimensions: int = 768,
        runtime: str = "auto",
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._ollama_model = ollama_model
        self._dimensions = dimensions
        self._runtime = runtime

    @property
    def runtime(self) -> str:
        runtime = self._runtime
        if runtime == "auto":
            try:
                req = Request(f"{self._ollama_url}/api/tags", method="GET")
                with urlopen(req, timeout=3):
                    return "ollama"
            except Exception:
                return "mock"
        return runtime

    def embed(self, text: str) -> list[float]:
        if self.runtime == "ollama":
            embedded = self._embed_with_ollama(text)
            if embedded is not None:
                return embedded[: self._dimensions]
        # Deterministic hash-based fallback
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for index in range(self._dimensions):
            byte = digest[index % len(digest)]
            values.append(round(byte / 255.0, 6))
        return values

    def _embed_with_ollama(self, text: str) -> list[float] | None:
        payload = {
            "model": self._ollama_model,
            "input": text,
        }
        data = json.dumps(payload).encode()
        req = Request(
            f"{self._ollama_url}/api/embed",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
            embeddings = body.get("embeddings", [])
            if embeddings and isinstance(embeddings[0], list):
                return [float(v) for v in embeddings[0]]
            return None
        except Exception:
            logger.warning("Ollama embedding failed, using hash fallback")
            return None
