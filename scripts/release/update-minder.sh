#!/usr/bin/env bash

set -euo pipefail

# ------------------------------------------------------------------
# Minder Update Script
#
# Checks for the latest release and upgrades the running deployment.
#
# Usage:
#   ./update-minder.sh                     # Auto-detect latest release
#   ./update-minder.sh --tag v0.3.0        # Update to a specific version
# ------------------------------------------------------------------

MINDER_DIR="${HOME}/.minder"
CURRENT_LINK="${MINDER_DIR}/current"
TARGET_TAG=""

for arg in "$@"; do
  case "$arg" in
    --tag)   shift; TARGET_TAG="${1:-}" ;;
    --tag=*) TARGET_TAG="${arg#*=}" ;;
    --help|-h)
      echo "Usage: $0 [--tag vX.Y.Z]"
      echo ""
      echo "  --tag vX.Y.Z   Update to a specific release version"
      echo "                  If omitted, fetches the latest release"
      exit 0
      ;;
  esac
  shift 2>/dev/null || true
done

# ------------------------------------------------------------------
# Step 1: Determine current and target versions
# ------------------------------------------------------------------

CURRENT_TAG=""
if [ -L "$CURRENT_LINK" ] && [ -f "$(readlink "$CURRENT_LINK")/.minder-release.json" ]; then
  CURRENT_TAG="$(python3 -c "import json; print(json.load(open('$(readlink "$CURRENT_LINK")/.minder-release.json'))['release_tag'])" 2>/dev/null || true)"
fi

if [ -z "$CURRENT_TAG" ]; then
  echo "No current Minder installation found at $CURRENT_LINK" >&2
  echo "Run the install script first." >&2
  exit 1
fi

# Read repo info from current installation
REPO_OWNER="$(python3 -c "import json; print(json.load(open('$(readlink "$CURRENT_LINK")/.minder-release.json'))['repo_owner'])")"
REPO_NAME="$(python3 -c "import json; print(json.load(open('$(readlink "$CURRENT_LINK")/.minder-release.json'))['repo_name'])")"

if [ -z "$TARGET_TAG" ]; then
  echo "Checking for latest release..."
  TARGET_TAG="$(curl -fsSL "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")"
fi

if [ "$CURRENT_TAG" = "$TARGET_TAG" ]; then
  echo "Already running the latest version: $CURRENT_TAG"
  exit 0
fi

echo "Current version: $CURRENT_TAG"
echo "Target version:  $TARGET_TAG"
echo ""

# ------------------------------------------------------------------
# Step 2: Download and run the new installer
# ------------------------------------------------------------------

INSTALLER_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${TARGET_TAG}/install-minder-${TARGET_TAG}.sh"

echo "Downloading installer for $TARGET_TAG..."
TEMP_INSTALLER="$(mktemp)"
curl -fsSL "$INSTALLER_URL" -o "$TEMP_INSTALLER"
chmod +x "$TEMP_INSTALLER"

echo "Running installer..."
bash "$TEMP_INSTALLER"
rm -f "$TEMP_INSTALLER"

# ------------------------------------------------------------------
# Step 3: Cleanup old release (optional)
# ------------------------------------------------------------------

OLD_DIR="${MINDER_DIR}/releases/${CURRENT_TAG}"
if [ -d "$OLD_DIR" ] && [ "$OLD_DIR" != "$(readlink "$CURRENT_LINK")" ]; then
  echo ""
  echo "Stopping old release containers..."
  if [ -f "$OLD_DIR/docker-compose.yml" ]; then
    docker compose --env-file "$OLD_DIR/.env" -f "$OLD_DIR/docker-compose.yml" down 2>/dev/null || true
  fi
  echo "Old release directory kept at: $OLD_DIR"
  echo "To remove it: rm -rf $OLD_DIR"
fi

echo ""
echo "Update complete: $CURRENT_TAG -> $TARGET_TAG"
