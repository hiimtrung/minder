#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${HOME}/.minder/models"
EMBED_URL="${MINDER_EMBED_MODEL_URL:-https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF/resolve/main/embeddinggemma-300M-Q8_0.gguf?download=true}"
LLM_URL="${MINDER_LLM_MODEL_URL:-https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-e2b-it-Q8_0.gguf?download=true}"
EMBED_FILE="${MODEL_DIR}/embeddinggemma-300M-Q8_0.gguf"
LLM_FILE="${MODEL_DIR}/gemma-4-e2b-it-Q8_0.gguf"
EMBED_SHA256="${MINDER_EMBED_MODEL_SHA256:-}"
LLM_SHA256="${MINDER_LLM_MODEL_SHA256:-}"

download_if_missing() {
  local url="$1"
  local target="$2"
  if [ -f "$target" ]; then
    echo "skip: $target"
    return
  fi
  mkdir -p "$(dirname "$target")"
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
download_if_missing "$LLM_URL" "$LLM_FILE"
verify_checksum "$EMBED_FILE" "$EMBED_SHA256"
verify_checksum "$LLM_FILE" "$LLM_SHA256"

echo "models ready in $MODEL_DIR"
