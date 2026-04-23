"""
LLM provider factory — selects the correct provider based on config.

Supported providers:
- ``litert``: LiteRT-LM (on-device, recommended for local LLM)

- ``openai``: OpenAI-compatible cloud API
"""

from __future__ import annotations

from minder.config import LLMConfig


def create_llm(config: LLMConfig):  # type: ignore[no-untyped-def]
    """Create an LLM client from the given configuration."""
    if config.provider == "litert":
        from minder.llm.litert import LiteRTModelLLM

        return LiteRTModelLLM(
            model_path=config.litert_model_path,
            backend=config.litert_backend,
            cache_dir=config.litert_cache_dir,
            context_length=config.context_length,
        )



    if config.provider == "openai":
        from minder.llm.openai import OpenAIFallbackLLM

        return OpenAIFallbackLLM(
            config.openai_api_key,
            config.openai_model,
            runtime="auto",
        )

    raise ValueError(f"Unknown LLM provider: {config.provider!r}")
