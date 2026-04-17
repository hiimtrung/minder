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

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command docker
require_command curl

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is required." >&2
  exit 1
fi

if [[ ! -d "$MODELS_DIR" ]]; then
  echo "Model directory not found: $MODELS_DIR" >&2
  echo "Populate ~/.minder/models or set MINDER_MODELS_DIR before running this installer." >&2
  exit 1
fi

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

Open:
  http://localhost:$PUBLIC_PORT/dashboard/setup
  http://localhost:$PUBLIC_PORT/sse

Useful commands:
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" ps
  docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" logs -f gateway
EOF