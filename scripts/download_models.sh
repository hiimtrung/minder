#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${HOME}/.minder/models"

# Embedding model (still GGUF for offline/fallback, but primary embedding now uses Docker Ollama)
EMBED_URL="${MINDER_EMBED_MODEL_URL:-https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF/resolve/main/embeddinggemma-300M-Q8_0.gguf?download=true}"
EMBED_FILE="${MODEL_DIR}/embeddinggemma-300M-Q8_0.gguf"
EMBED_SHA256="${MINDER_EMBED_MODEL_SHA256:-}"

# LiteRT-LM model for local LLM inference
LITERT_URL="${MINDER_LITERT_MODEL_URL:-https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm?download=true}"
LITERT_FILE="${MODEL_DIR}/gemma-4-E2B-it.litertlm"
LITERT_SHA256="${MINDER_LITERT_MODEL_SHA256:-}"

download_if_missing() {
  local url="$1"
  local target="$2"
  if [ -f "$target" ]; then
    echo "skip: $target"
    return
  fi
  mkdir -p "$(dirname "$target")"
  echo "Downloading $(basename "$target")..."
  curl -L "$url" -o "$target"
}

verify_checksum() {
  local target="$1"
  local expected="$2"
  if [ -z "$expected" ]; then
    return
  fi
  local actual
  actual="$(shasum -a 256 "$target" | awk '{print $1}')"
  if [ "$actual" != "$expected" ]; then
    echo "checksum mismatch for $target" >&2
    exit 1
  fi
}

download_if_missing "$EMBED_URL" "$EMBED_FILE"
download_if_missing "$LITERT_URL" "$LITERT_FILE"
verify_checksum "$EMBED_FILE" "$EMBED_SHA256"
verify_checksum "$LITERT_FILE" "$LITERT_SHA256"

echo "models ready in $MODEL_DIR"
