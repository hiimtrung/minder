#!/usr/bin/env bash
set -euo pipefail

# llama-cpp-python downloads GGUF models automatically via Llama.from_pretrained()
# when the server starts. No manual download is required.
#
# Default model repos (override via env vars):
#   LLM:       MINDER_LLM__LLAMA_CPP_MODEL_REPO   (default: ggml-org/gemma-4-E2B-it-GGUF)
#   Embedding: MINDER_EMBEDDING__LLAMA_CPP_MODEL_REPO (default: ggml-org/embeddinggemma-300M-GGUF)
#
# The HuggingFace cache is stored in ~/.cache/huggingface/ by default.

echo "GGUF models are downloaded automatically by llama-cpp-python on first server start."
echo "  LLM repo:       ${MINDER_LLM__LLAMA_CPP_MODEL_REPO:-ggml-org/gemma-4-E2B-it-GGUF}"
echo "  Embedding repo: ${MINDER_EMBEDDING__LLAMA_CPP_MODEL_REPO:-ggml-org/embeddinggemma-300M-GGUF}"
