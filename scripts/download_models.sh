#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${HOME}/.minder/models"


# LiteRT-LM model for local LLM inference
LITERT_URL="${MINDER_LITERT_MODEL_URL:-https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it.litertlm?download=true}"
LITERT_FILE="${MODEL_DIR}/gemma-4-E4B-it.litertlm"
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

download_if_missing "$LITERT_URL" "$LITERT_FILE"
verify_checksum "$LITERT_FILE" "$LITERT_SHA256"

echo "models ready in $MODEL_DIR"
