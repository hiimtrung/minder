#!/usr/bin/env bash

# Minder native installer — macOS and Linux.
# Placeholders substituted at release time by the CI pipeline.
#
# macOS:  mounts the .dmg and copies Minder.app to /Applications.
# Linux:  installs the .deb (when dpkg + sudo available) or places the
#         AppImage in ~/.local/bin as a fallback.

set -euo pipefail

REPO_OWNER="__REPO_OWNER__"
REPO_NAME="__REPO_NAME__"
RELEASE_TAG="__RELEASE_TAG__"

VERSION="${RELEASE_TAG#v}"   # strip leading 'v'
RELEASE_BASE_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${RELEASE_TAG}"
MINDER_DIR="${HOME}/.minder"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

download() {
  local url="$1" dest="$2"
  echo "  Downloading $(basename "$dest")..."
  curl -fsSL --progress-bar "$url" -o "$dest"
}

# ------------------------------------------------------------------
# Platform detection
# ------------------------------------------------------------------

OS="$(uname -s)"
ARCH="$(uname -m)"

require_command curl

# ------------------------------------------------------------------
# macOS install
# ------------------------------------------------------------------

install_macos() {
  case "$ARCH" in
    arm64)   ARCH_SUFFIX="aarch64" ;;
    x86_64)  ARCH_SUFFIX="x64" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac

  local dmg_name="Minder_${VERSION}_${ARCH_SUFFIX}.dmg"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local tmp_dmg="${tmp_dir}/minder.dmg"

  download "${RELEASE_BASE_URL}/${dmg_name}" "$tmp_dmg"

  echo "  Mounting disk image..."
  local mount_output
  mount_output="$(hdiutil attach "$tmp_dmg" -nobrowse -quiet)"
  local mount_point
  mount_point="$(echo "$mount_output" | awk 'END{print $NF}')"

  echo "  Installing Minder.app → /Applications/"
  cp -r "${mount_point}/Minder.app" /Applications/

  echo "  Unmounting..."
  hdiutil detach "$mount_point" -quiet
  rm -rf "$tmp_dir"

  echo "Minder installed at /Applications/Minder.app"
}

# ------------------------------------------------------------------
# Linux install — .deb preferred, AppImage fallback
# ------------------------------------------------------------------

install_linux_deb() {
  case "$ARCH" in
    x86_64)          ARCH_SUFFIX="amd64" ;;
    aarch64|arm64)   ARCH_SUFFIX="arm64" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac

  local deb_name="minder_${VERSION}_${ARCH_SUFFIX}.deb"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local tmp_deb="${tmp_dir}/minder.deb"

  download "${RELEASE_BASE_URL}/${deb_name}" "$tmp_deb"

  echo "  Installing .deb package (sudo required)..."
  sudo dpkg -i "$tmp_deb"
  rm -rf "$tmp_dir"

  echo "Minder installed. Run: minder-app"
}

install_linux_appimage() {
  case "$ARCH" in
    x86_64)          ARCH_SUFFIX="amd64" ;;
    aarch64|arm64)   ARCH_SUFFIX="aarch64" ;;
    *)
      echo "Unsupported architecture: $ARCH" >&2
      exit 1
      ;;
  esac

  local app_name="Minder_${VERSION}_${ARCH_SUFFIX}.AppImage"
  local install_dir="${HOME}/.local/bin"
  mkdir -p "$install_dir"

  download "${RELEASE_BASE_URL}/${app_name}" "${install_dir}/Minder.AppImage"
  chmod +x "${install_dir}/Minder.AppImage"

  echo "Minder AppImage installed: ${install_dir}/Minder.AppImage"
  if ! echo "$PATH" | grep -q "${install_dir}"; then
    echo "  Add ${install_dir} to your PATH to run it as 'Minder.AppImage'."
  fi
}

# ------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------

echo ""
echo "Installing Minder ${RELEASE_TAG}..."
echo ""

case "$OS" in
  Darwin)
    install_macos
    ;;
  Linux)
    if command -v dpkg >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
      install_linux_deb
    else
      install_linux_appimage
    fi
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# ------------------------------------------------------------------
# Save release metadata (used by update/uninstall scripts)
# ------------------------------------------------------------------

mkdir -p "$MINDER_DIR"
cat > "${MINDER_DIR}/.minder-release.json" <<EOF
{
  "repo_owner": "${REPO_OWNER}",
  "repo_name": "${REPO_NAME}",
  "repository": "https://github.com/${REPO_OWNER}/${REPO_NAME}",
  "release_tag": "${RELEASE_TAG}"
}
EOF

echo ""
echo "Minder ${RELEASE_TAG} is ready."
echo ""
echo "First run:"
echo "  macOS:  open /Applications/Minder.app"
echo "  Linux:  minder-app   (deb)  or  Minder.AppImage  (AppImage)"
echo ""
echo "Dashboard: http://localhost:8800/dashboard/setup"
echo "MCP SSE:   http://localhost:8800/sse"
echo ""
echo "CLI:"
echo "  uv tool install minder-cli"
echo "  minder login --client-key mkc_... --server-url http://localhost:8800/sse"
