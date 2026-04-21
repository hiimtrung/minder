#!/usr/bin/env bash

set -euo pipefail

REPO_OWNER="__REPO_OWNER__"
REPO_NAME="__REPO_NAME__"
RELEASE_TAG="__RELEASE_TAG__"

INSTALL_DIR="${MINDER_INSTALL_DIR:-$HOME/.minder/releases/$RELEASE_TAG}"
CURRENT_LINK="${MINDER_CURRENT_LINK:-$HOME/.minder/current}"
PUBLIC_PORT="${MINDER_PORT:-8800}"
MILVUS_PORT="${MILVUS_PORT:-19530}"
API_IMAGE="ghcr.io/${REPO_OWNER}/minder-api:${RELEASE_TAG}"
DASHBOARD_IMAGE="ghcr.io/${REPO_OWNER}/minder-dashboard:${RELEASE_TAG}"
RELEASE_BASE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${RELEASE_TAG}"

LLM_MODEL="${MINDER_LLM_MODEL:-gemma4:e4b}"
EMBEDDING_MODEL="${MINDER_EMBEDDING_MODEL:-embeddinggemma}"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

detect_os() {
  case "$(uname -s)" in
    Linux*)  echo "linux" ;;
    Darwin*) echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *) echo "unknown" ;;
  esac
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
# Step 2: Install Ollama if missing
# ------------------------------------------------------------------

install_ollama() {
  local os="$1"
  echo "Ollama not found. Installing..."

  case "$os" in
    linux)
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
    macos)
      if command -v brew >/dev/null 2>&1; then
        brew install ollama
      else
        echo "Please install Ollama manually from https://ollama.com/download" >&2
        echo "After installing, run this script again." >&2
        exit 1
      fi
      ;;
    *)
      echo "Unsupported OS for automatic Ollama installation." >&2
      echo "Please install Ollama manually from https://ollama.com/download" >&2
      exit 1
      ;;
  esac
}

OS="$(detect_os)"

if ! command -v ollama >/dev/null 2>&1; then
  install_ollama "$OS"
fi

# Ensure Ollama is running
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama service..."
  case "$OS" in
    linux)
      if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl start ollama 2>/dev/null || ollama serve &
      else
        ollama serve &
      fi
      ;;
    macos)
      ollama serve &
      ;;
  esac
  # Wait for Ollama to be ready
  echo "Waiting for Ollama to start..."
  for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    if [ "$i" -eq 30 ]; then
      echo "Ollama did not start within 30 seconds." >&2
      exit 1
    fi
    sleep 1
  done
fi

echo "Ollama is running."

# ------------------------------------------------------------------
# Step 3: Pull required models
# ------------------------------------------------------------------

pull_model() {
  local model_name="$1"
  echo "Checking model: $model_name"
  if ollama list 2>/dev/null | grep -q "^${model_name}"; then
    echo "  Model $model_name is already available."
  else
    echo "  Pulling $model_name (this may take a few minutes)..."
    ollama pull "$model_name"
  fi
}

pull_model "$LLM_MODEL"
pull_model "$EMBEDDING_MODEL"

echo "All required models are ready."

# ------------------------------------------------------------------
# Step 4: Verify pre-conditions
# ------------------------------------------------------------------

echo ""
echo "Pre-flight checks:"
echo "  [✓] Docker with Compose plugin"
echo "  [✓] Ollama running at http://localhost:11434"
echo "  [✓] LLM model: $LLM_MODEL"
echo "  [✓] Embedding model: $EMBEDDING_MODEL"
echo ""

# ------------------------------------------------------------------
# Step 5: Download release assets and start Docker Compose
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
MINDER_OLLAMA_URL=http://host.docker.internal:11434
MINDER_LLM_MODEL=$LLM_MODEL
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
Ollama: http://localhost:11434
LLM model: $LLM_MODEL
Embedding model: $EMBEDDING_MODEL

Open:
  http://localhost:$PUBLIC_PORT/dashboard/setup
  http://localhost:$PUBLIC_PORT/sse

Useful commands:
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" ps
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" logs -f gateway
EOF