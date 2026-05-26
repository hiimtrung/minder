#!/usr/bin/env bash

# Minder Uninstall Script
#
# Usage:
#   ./uninstall-minder.sh               # Full uninstall (app + all data)
#   ./uninstall-minder.sh --keep-data   # Remove app only, keep ~/.minder/ data

set -euo pipefail

KEEP_DATA=false
for arg in "$@"; do
  case "$arg" in
    --keep-data) KEEP_DATA=true ;;
    --help|-h)
      echo "Usage: $0 [--keep-data]"
      echo ""
      echo "  --keep-data   Keep downloaded models and data in ~/.minder/"
      echo "                Only removes the app binary / package"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

OS="$(uname -s)"
MINDER_DIR="${HOME}/.minder"

# ------------------------------------------------------------------
# Step 1: Remove the installed app
# ------------------------------------------------------------------

case "$OS" in
  Darwin)
    if [ -d /Applications/Minder.app ]; then
      echo "Removing /Applications/Minder.app..."
      rm -rf /Applications/Minder.app
    else
      echo "Minder.app not found in /Applications — skipping."
    fi
    ;;
  Linux)
    # .deb install
    if command -v dpkg >/dev/null 2>&1 && dpkg -l minder >/dev/null 2>&1; then
      echo "Removing minder .deb package (sudo required)..."
      sudo dpkg -r minder
    fi
    # AppImage install
    if [ -f "${HOME}/.local/bin/Minder.AppImage" ]; then
      echo "Removing ${HOME}/.local/bin/Minder.AppImage..."
      rm -f "${HOME}/.local/bin/Minder.AppImage"
    fi
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# ------------------------------------------------------------------
# Step 2: Handle data directory
# ------------------------------------------------------------------

if [ "$KEEP_DATA" = true ]; then
  echo ""
  echo "Minder app removed."
  echo "Data kept at: ${MINDER_DIR}/"
  echo ""
  echo "To fully remove data later:"
  echo "  rm -rf \"${MINDER_DIR}\""
  exit 0
fi

if [ -d "$MINDER_DIR" ]; then
  echo "Removing Minder data directory: ${MINDER_DIR}/"
  rm -rf "$MINDER_DIR"
fi

echo ""
echo "Minder fully uninstalled."
echo "  - App removed"
echo "  - Data directory removed: ${MINDER_DIR}"
