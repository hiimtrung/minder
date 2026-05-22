"""
Domain Interface — LLM Provider.

Infrastructure adapters (LlamaCppLLM, OpenAIFallbackLLM, etc.)
implement this protocol. Application use-cases depend only on this interface.

NOTE: This interface is intentionally decoupled from graph/state so that
domain-layer code never depends on infrastructure graph libraries.
"""

from __future__ import annotations

from typing import Any, Protocol


class ILLMProvider(Protocol):
    """Contract for LLM text completion."""

    @property
    def runtime(self) -> str: ...

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 1000,
        temperature: float = 0.1,
        fallback: str = "",
    ) -> str: ...
