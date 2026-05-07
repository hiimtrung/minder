#!/usr/bin/env bash
set -euo pipefail

# Pre-download GGUF models to MINDER_MODELS_DIR so the container doesn't
# fetch them from HuggingFace on every start.
#
# The container sets HUGGINGFACE_HUB_CACHE=/models (mounted from MINDER_MODELS_DIR),
# so this script must download to the same directory using the same env var.
#
# Usage:
#   ./scripts/download_models.sh
#   MINDER_MODELS_DIR=/custom/path ./scripts/download_models.sh

MODELS_DIR="${MINDER_MODELS_DIR:-$HOME/.minder/models}"
LLM_REPO="${MINDER_LLM__LLAMA_CPP_MODEL_REPO:-ggml-org/gemma-4-E2B-it-GGUF}"
LLM_FILE="${MINDER_LLM__LLAMA_CPP_MODEL_FILE:-gemma-4-E2B-it-Q8_0.gguf}"
EMBEDDING_REPO="${MINDER_EMBEDDING__LLAMA_CPP_MODEL_REPO:-ggml-org/embeddinggemma-300M-GGUF}"
EMBEDDING_FILE="${MINDER_EMBEDDING__LLAMA_CPP_MODEL_FILE:-embeddinggemma-300M-Q8_0.gguf}"

mkdir -p "$MODELS_DIR"

echo "Downloading models to: $MODELS_DIR"
echo "  LLM:       $LLM_REPO / $LLM_FILE"
echo "  Embedding: $EMBEDDING_REPO / $EMBEDDING_FILE"
echo ""

if ! command -v huggingface-cli &>/dev/null; then
    echo "Error: huggingface-cli not found. Install it with: pip install huggingface-hub[cli]"
    exit 1
fi

HUGGINGFACE_HUB_CACHE="$MODELS_DIR" huggingface-cli download "$LLM_REPO" "$LLM_FILE"
HUGGINGFACE_HUB_CACHE="$MODELS_DIR" huggingface-cli download "$EMBEDDING_REPO" --include "$EMBEDDING_FILE"

echo ""
echo "Done. Models cached at: $MODELS_DIR"
echo "Run 'docker compose up' to start the server — models will load from disk."
