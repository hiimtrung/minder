#!/usr/bin/env bash

# Minder Update Script
#
# Checks for the latest release and re-runs the installer for the target version.
#
# Usage:
#   ./update-minder.sh                  # Update to the latest release
#   ./update-minder.sh --tag v0.7.0     # Update to a specific version

set -euo pipefail

MINDER_DIR="${HOME}/.minder"
RELEASE_META="${MINDER_DIR}/.minder-release.json"
TARGET_TAG=""

for arg in "$@"; do
  case "$arg" in
    --tag=*) TARGET_TAG="${arg#*=}" ;;
    --tag)   shift; TARGET_TAG="${1:-}" ;;
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
# Step 1: Read current installation metadata
# ------------------------------------------------------------------

if [ ! -f "$RELEASE_META" ]; then
  echo "No Minder installation found at ${MINDER_DIR}." >&2
  echo "Run the install script first." >&2
  exit 1
fi

CURRENT_TAG="$(python3 -c "import json; print(json.load(open('${RELEASE_META}'))['release_tag'])")"
REPO_OWNER="$(python3 -c "import json; print(json.load(open('${RELEASE_META}'))['repo_owner'])")"
REPO_NAME="$(python3 -c "import json; print(json.load(open('${RELEASE_META}'))['repo_name'])")"

# ------------------------------------------------------------------
# Step 2: Determine target version
# ------------------------------------------------------------------

if [ -z "$TARGET_TAG" ]; then
  echo "Checking for latest release..."
  TARGET_TAG="$(curl -fsSL "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")"
fi

if [ "$CURRENT_TAG" = "$TARGET_TAG" ]; then
  echo "Already on the latest version: $CURRENT_TAG"
  exit 0
fi

echo "Current version: $CURRENT_TAG"
echo "Target version:  $TARGET_TAG"
echo ""

# ------------------------------------------------------------------
# Step 3: Download and run the new installer
# ------------------------------------------------------------------

INSTALLER_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${TARGET_TAG}/install-minder-${TARGET_TAG}.sh"

echo "Downloading installer for $TARGET_TAG..."
TEMP_INSTALLER="$(mktemp)"
curl -fsSL "$INSTALLER_URL" -o "$TEMP_INSTALLER"
chmod +x "$TEMP_INSTALLER"

echo "Running installer..."
bash "$TEMP_INSTALLER"
rm -f "$TEMP_INSTALLER"

echo ""
echo "Update complete: $CURRENT_TAG → $TARGET_TAG"
