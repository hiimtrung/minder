# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the minder-server binary.
# Used by `make bundle` to produce a single executable for Tauri sidecar packaging.
#
# Usage:
#   uv run pyinstaller minder-server.spec
#
# Output: dist/minder-server  (or dist/minder-server.exe on Windows)
#
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect all sub-packages that use dynamic imports.
# collect_all returns (datas, binaries, hiddenimports) tuples.
minder_d, minder_b, minder_h = collect_all("minder")
milvus_d, milvus_b, milvus_h = collect_all("pymilvus")
turbovec_d, turbovec_b, turbovec_h = collect_all("turbovec")
langgraph_d, langgraph_b, langgraph_h = collect_all("langgraph")
litellm_d, litellm_b, litellm_h = collect_all("litellm")
mcp_d, mcp_b, mcp_h = collect_all("mcp")

# ---------------------------------------------------------------------------
# Native deployment: bundle dashboard dist + config for self-contained app.
# The Tauri sidecar runs from inside the .app bundle / AppImage — CWD won't
# contain these files, so we embed them next to the binary.
# ---------------------------------------------------------------------------
project_root = Path(SPECPATH)

native_datas = []

# Dashboard — pre-built Astro static files
dashboard_dist = project_root / "src" / "dashboard" / "dist"
if dashboard_dist.is_dir():
    native_datas.append((str(dashboard_dist), "dashboard_dist"))

# Default configuration (users can override via env vars or ~/.minder/)
minder_toml = project_root / "minder.toml"
if minder_toml.is_file():
    native_datas.append((str(minder_toml), "."))

a = Analysis(
    [str(Path("src") / "minder" / "server.py")],
    pathex=[str(Path("src"))],
    binaries=minder_b + milvus_b + turbovec_b + langgraph_b + litellm_b + mcp_b,
    datas=minder_d + milvus_d + turbovec_d + langgraph_d + litellm_d + mcp_d + native_datas,
    hiddenimports=(
        minder_h + milvus_h + turbovec_h + langgraph_h + litellm_h + mcp_h
        + collect_submodules("aiosqlite")
        + collect_submodules("sqlalchemy")
        + collect_submodules("passlib")
        + collect_submodules("fastapi")
        + collect_submodules("pydantic")
        + collect_submodules("pydantic_settings")
        + collect_submodules("uvicorn")
        + collect_submodules("starlette")
        + [
            "sqlalchemy.dialects.sqlite",
            "sqlalchemy.dialects.sqlite.aiosqlite",
            "aiosqlite",
            "passlib.handlers.bcrypt",
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["qdrant_client"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="minder-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

