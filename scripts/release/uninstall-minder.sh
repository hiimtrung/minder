#!/usr/bin/env bash

set -euo pipefail

# ------------------------------------------------------------------
# Minder Uninstall Script
#
# Usage:
#   ./uninstall-minder.sh               # Full uninstall (removes everything)
#   ./uninstall-minder.sh --keep-data   # Keeps Ollama, models, Docker volumes, config
# ------------------------------------------------------------------

KEEP_DATA=false
for arg in "$@"; do
  case "$arg" in
    --keep-data) KEEP_DATA=true ;;
    --help|-h)
      echo "Usage: $0 [--keep-data]"
      echo ""
      echo "  --keep-data   Keep downloaded models, Docker volumes, and config files"
      echo "                Only removes Minder containers and release directories"
      exit 0
      ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

MINDER_DIR="${HOME}/.minder"
CURRENT_LINK="${MINDER_DIR}/current"

# ------------------------------------------------------------------
# Step 1: Stop and remove Minder Docker containers
# ------------------------------------------------------------------

echo "Stopping Minder containers..."

if [ -L "$CURRENT_LINK" ]; then
  INSTALL_DIR="$(readlink "$CURRENT_LINK")"
  if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    docker compose --env-file "$INSTALL_DIR/.env" -f "$INSTALL_DIR/docker-compose.yml" down 2>/dev/null || true
  fi
fi

# Also try all release directories
if [ -d "${MINDER_DIR}/releases" ]; then
  for release_dir in "${MINDER_DIR}/releases"/*/; do
    if [ -f "${release_dir}docker-compose.yml" ]; then
      docker compose --env-file "${release_dir}.env" -f "${release_dir}docker-compose.yml" down 2>/dev/null || true
    fi
  done
fi

echo "Minder containers stopped."

# ------------------------------------------------------------------
# Step 2: Remove release directories and current link
# ------------------------------------------------------------------

echo "Removing release directories..."
rm -rf "${MINDER_DIR}/releases"
rm -f "$CURRENT_LINK"

if [ "$KEEP_DATA" = true ]; then
  echo ""
  echo "Uninstall complete (--keep-data mode)."
  echo ""
  echo "Kept:"
  echo "  - Downloaded models"
  echo "  - Docker volumes (mongodb-data, redis-data, milvus-data, etc.)"
  echo "  - Config files in ${MINDER_DIR}/"
  echo ""
  echo "To remove Docker volumes manually:"
  echo "  docker volume ls | grep minder"
  echo "  docker volume rm <volume-name>"
  exit 0
fi

# ------------------------------------------------------------------
# Step 3: Full cleanup (only when --keep-data is NOT set)
# ------------------------------------------------------------------

echo "Removing Docker volumes..."
for vol in $(docker volume ls -q 2>/dev/null | grep -E "(mongodb|redis|milvus|etcd|minio)" || true); do
  echo "  Removing volume: $vol"
  docker volume rm "$vol" 2>/dev/null || true
done

echo "Removing Minder config directory..."
rm -rf "$MINDER_DIR"



echo ""
echo "Minder has been fully uninstalled."
echo "  - All containers stopped and removed"
echo "  - Docker volumes removed"

echo "  - Config directory removed: ${MINDER_DIR}"
