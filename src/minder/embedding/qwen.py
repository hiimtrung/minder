from __future__ import annotations

import hashlib
from pathlib import Path


class QwenEmbeddingProvider:
    def __init__(self, model_path: str, dimensions: int = 16, runtime: str = "mock") -> None:
        self._model_path = model_path
        self._dimensions = dimensions
        self._runtime = runtime

    @property
    def runtime(self) -> str:
        runtime = self._runtime
        if runtime == "auto":
            return "llama_cpp" if Path(self._model_path).expanduser().exists() else "mock"
        return runtime

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for index in range(self._dimensions):
            byte = digest[index % len(digest)]
            values.append(round(byte / 255.0, 6))
        return values
