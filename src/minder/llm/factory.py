"""
LLM provider factory — selects the correct provider based on config.

Supported providers:
- ``llama_cpp``: llama-cpp-python GGUF inference (on-device, recommended for local LLM)
- ``openai``: OpenAI-compatible cloud API
"""

from __future__ import annotations

from minder.config import LLMConfig


def create_llm(config: LLMConfig):  # type: ignore[no-untyped-def]
    """Create an LLM client from the given configuration."""
    if config.provider == "llama_cpp":
        from minder.llm.llama_cpp_llm import LlamaCppLLM

        return LlamaCppLLM(
            model_repo=config.llama_cpp_model_repo,
            model_file=config.llama_cpp_model_file,
            context_length=config.context_length,
            temperature=config.temperature,
        )

    if config.provider == "openai":
        from minder.llm.openai import OpenAIFallbackLLM

        return OpenAIFallbackLLM(
            config.openai_api_key,
            config.openai_model,
            runtime="auto",
        )

    raise ValueError(f"Unknown LLM provider: {config.provider!r}")
