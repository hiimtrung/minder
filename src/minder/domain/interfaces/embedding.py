"""
Domain Interface — Embedding Provider.

Infrastructure adapters (LocalEmbeddingProvider, OpenAIEmbedding, etc.)
implement this protocol. Application use-cases depend only on this interface.
"""

from __future__ import annotations

from typing import Protocol


class IEmbeddingProvider(Protocol):
    """Contract for converting text into a vector embedding."""

    def embed(self, text: str) -> list[float]: ...
