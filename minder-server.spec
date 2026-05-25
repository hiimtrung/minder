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
langgraph_d, langgraph_b, langgraph_h = collect_all("langgraph")
litellm_d, litellm_b, litellm_h = collect_all("litellm")
mcp_d, mcp_b, mcp_h = collect_all("mcp")

a = Analysis(
    [str(Path("src") / "minder" / "server.py")],
    pathex=[str(Path("src"))],
    binaries=minder_b + milvus_b + langgraph_b + litellm_b + mcp_b,
    datas=minder_d + milvus_d + langgraph_d + litellm_d + mcp_d,
    hiddenimports=(
        minder_h + milvus_h + langgraph_h + litellm_h + mcp_h
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
    [],
    exclude_binaries=True,
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="minder-server",
)
