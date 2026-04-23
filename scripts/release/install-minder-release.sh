#!/usr/bin/env bash

set -euo pipefail

REPO_OWNER="__REPO_OWNER__"
REPO_NAME="__REPO_NAME__"
RELEASE_TAG="__RELEASE_TAG__"

INSTALL_DIR="${MINDER_INSTALL_DIR:-$HOME/.minder/releases/$RELEASE_TAG}"
CURRENT_LINK="${MINDER_CURRENT_LINK:-$HOME/.minder/current}"
MODELS_DIR="${MINDER_MODELS_DIR:-$HOME/.minder/models}"
PUBLIC_PORT="${MINDER_PORT:-8800}"
MILVUS_PORT="${MILVUS_PORT:-19530}"
API_IMAGE="ghcr.io/${REPO_OWNER}/minder-api:${RELEASE_TAG}"
DASHBOARD_IMAGE="ghcr.io/${REPO_OWNER}/minder-dashboard:${RELEASE_TAG}"
RELEASE_BASE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${RELEASE_TAG}"

EMBEDDING_MODEL="${MINDER_EMBEDDING_MODEL:-mixedbread-ai/mxbai-embed-large-v1}"
LITERT_MODEL_URL="${MINDER_LITERT_MODEL_URL:-https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it.litertlm?download=true}"
LITERT_MODEL_FILE="gemma-4-E4B-it.litertlm"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

# ------------------------------------------------------------------
# Step 1: Verify Docker
# ------------------------------------------------------------------

require_command docker
require_command curl

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is required." >&2
  exit 1
fi

# ------------------------------------------------------------------
# Step 2: Download LiteRT-LM model
# ------------------------------------------------------------------

mkdir -p "$MODELS_DIR"

if [ -f "$MODELS_DIR/$LITERT_MODEL_FILE" ]; then
  echo "LiteRT-LM model already exists: $MODELS_DIR/$LITERT_MODEL_FILE"
else
  echo "Downloading LiteRT-LM model (this may take a few minutes)..."
  curl -L "$LITERT_MODEL_URL" -o "$MODELS_DIR/$LITERT_MODEL_FILE"
fi

echo "LiteRT-LM model ready."

# ------------------------------------------------------------------
# Step 3: Verify pre-conditions
# ------------------------------------------------------------------

echo ""
echo "Pre-flight checks:"
echo "  [✓] Docker with Compose plugin"
echo "  [✓] LiteRT-LM model: $LITERT_MODEL_FILE"
echo "  [✓] Embedding model (FastEmbed): $EMBEDDING_MODEL"
echo ""

# ------------------------------------------------------------------
# Step 4: Download release assets and start Docker Compose
# ------------------------------------------------------------------

mkdir -p "$INSTALL_DIR"
mkdir -p "$(dirname "$CURRENT_LINK")"

curl -fsSL "$RELEASE_BASE_URL/docker-compose.yml" -o "$INSTALL_DIR/docker-compose.yml"
curl -fsSL "$RELEASE_BASE_URL/Caddyfile" -o "$INSTALL_DIR/Caddyfile"

cat > "$INSTALL_DIR/.env" <<EOF
MINDER_PORT=$PUBLIC_PORT
MILVUS_PORT=$MILVUS_PORT
MINDER_API_IMAGE=$API_IMAGE
MINDER_DASHBOARD_IMAGE=$DASHBOARD_IMAGE
MINDER_MODELS_DIR=$MODELS_DIR
MINDER_EMBEDDING_MODEL=$EMBEDDING_MODEL
OPENAI_API_KEY=${OPENAI_API_KEY:-}
EOF

cat > "$INSTALL_DIR/.minder-release.json" <<EOF
{
  "repo_owner": "$REPO_OWNER",
  "repo_name": "$REPO_NAME",
  "repository": "https://github.com/$REPO_OWNER/$REPO_NAME",
  "release_tag": "$RELEASE_TAG"
}
EOF

docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" pull
docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" up -d
ln -sfn "$INSTALL_DIR" "$CURRENT_LINK"

cat <<EOF
Minder release $RELEASE_TAG is starting.

Deployment directory: $INSTALL_DIR
Current release link: $CURRENT_LINK
API image: $API_IMAGE
Dashboard image: $DASHBOARD_IMAGE
LiteRT-LM model: $MODELS_DIR/$LITERT_MODEL_FILE
Embedding: FastEmbed ($EMBEDDING_MODEL)

Open:
  http://localhost:$PUBLIC_PORT/dashboard/setup
  http://localhost:$PUBLIC_PORT/sse

Useful commands:
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" ps
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" logs -f gateway
EOF
