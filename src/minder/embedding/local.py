from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from minder.runtime import load_attr, module_available


class LocalEmbeddingProvider:
    def __init__(self, model_path: str, dimensions: int = 768, runtime: str = "mock") -> None:
        self._model_path = model_path
        self._dimensions = dimensions
        self._runtime = runtime
        self._client: Any | None = None

    @property
    def runtime(self) -> str:
        runtime = self._runtime
        if runtime == "auto":
            if Path(self._model_path).expanduser().exists() and module_available("llama_cpp"):
                return "llama_cpp"
            return "mock"
        return runtime

    def embed(self, text: str) -> list[float]:
        if self.runtime == "llama_cpp":
            embedded = self._embed_with_llama_cpp(text)
            if embedded is not None:
                return embedded[: self._dimensions]
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for index in range(self._dimensions):
            byte = digest[index % len(digest)]
            values.append(round(byte / 255.0, 6))
        return values

    def _embed_with_llama_cpp(self, text: str) -> list[float] | None:
        client = self._llama_client()
        if client is None:
            return None
        response = client.embed(text)
        if isinstance(response, list):
            return [float(value) for value in response]
        data = response.get("data", []) if isinstance(response, dict) else []
        if not data:
            return None
        embedding = data[0].get("embedding", [])
        return [float(value) for value in embedding]

    def _llama_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        llama_cls = load_attr("llama_cpp", "Llama")
        if llama_cls is None:
            return None
        try:
            self._client = llama_cls(
                model_path=str(Path(self._model_path).expanduser()),
                embedding=True,
                verbose=False,
            )
        except Exception:
            return None
        return self._client