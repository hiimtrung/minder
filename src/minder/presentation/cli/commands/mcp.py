from __future__ import annotations

import argparse
import platform
import re
from pathlib import Path
from typing import Any

from ..utils.common import (
    load_json,
    write_json,
    mcp_url,
    sse_url,
    appdata_dir,
)
from ..utils.config import require_client_settings

_LOCAL_MCP_TARGETS = ("vscode", "cursor", "claude-code", "antigravity")
_ALL_MCP_TARGETS = (*_LOCAL_MCP_TARGETS, "codex")

# Matches [mcp_servers.minder] and all its key/value lines up to the next
# section header or end of file. [^\[] also matches newlines in Python.
_CODEX_SECTION_RE = re.compile(r"^\[mcp_servers\.minder\][^\[]*", re.MULTILINE)


def _global_target_path(target: str) -> Path:
    system = platform.system()
    if target == "vscode":
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "mcp-servers.json"
        if system == "Windows":
            return appdata_dir() / "Code" / "User" / "globalStorage" / "mcp-servers.json"
        return Path.home() / ".config" / "Code" / "User" / "globalStorage" / "mcp-servers.json"
    if target == "cursor":
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "mcp-servers.json"
        if system == "Windows":
            return appdata_dir() / "Cursor" / "User" / "globalStorage" / "mcp-servers.json"
        return Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "mcp-servers.json"
    if target == "claude-code":
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if system == "Windows":
            return appdata_dir() / "Claude" / "claude_desktop_config.json"
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    if target == "antigravity":
        return Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    if target == "codex":
        return Path.home() / ".codex" / "config.toml"
    raise ValueError(f"Unknown global target: {target}")


def _codex_mcp_section(url: str, client_key: str) -> str:
    return (
        "[mcp_servers.minder]\n"
        f'url = "{url}"\n'
        f'http_headers = {{ "X-Minder-Client-Key" = "{client_key}" }}\n'
    )


def _install_codex_mcp(url: str, client_key: str) -> None:
    path = _global_target_path("codex")
    new_section = _codex_mcp_section(url, client_key)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _CODEX_SECTION_RE.search(existing):
        updated = _CODEX_SECTION_RE.sub(new_section, existing)
    else:
        updated = existing.rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += new_section
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def _uninstall_codex_mcp() -> bool:
    path = _global_target_path("codex")
    if not path.is_file():
        return False
    existing = path.read_text(encoding="utf-8")
    if not _CODEX_SECTION_RE.search(existing):
        return False
    updated = _CODEX_SECTION_RE.sub("", existing).strip("\n")
    if updated:
        path.write_text(updated + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return True


def local_target_path(target: str, cwd: Path) -> Path:
    if target == "vscode":
        return cwd / ".vscode" / "mcp.json"
    if target == "cursor":
        return cwd / ".cursor" / "mcp.json"
    if target == "claude-code":
        return cwd / ".claude" / "mcp.json"
    if target == "antigravity":
        del cwd
        return Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    raise ValueError(f"Unknown local target: {target}")


def _target_root_key(target: str) -> str:
    if target == "vscode":
        return "servers"
    return "mcpServers"


def _target_entry(
    target: str,
    protocol: str,
    client_key: str,
    server_url: str | None,
) -> dict[str, Any]:
    if target == "antigravity" and protocol != "stdio":
        return {
            "serverUrl": mcp_url(server_url or ""),
            "headers": {"X-Minder-Client-Key": client_key},
        }

    if target == "vscode" and protocol != "stdio":
        return {
            "type": "sse",
            "url": sse_url(server_url or ""),
            "headers": {"X-Minder-Client-Key": client_key},
        }
        
    if protocol == "stdio":
        entry = {
            "command": "uv",
            "args": ["run", "python", "-m", "minder.server"],
            "env": {
                "MINDER_CLIENT_API_KEY": client_key,
                "MINDER_SERVER__TRANSPORT": "stdio",
            },
        }
        if target == "vscode":
            entry["type"] = "stdio"
        return entry
    # sse
    if target == "claude-code":
        return {"url": sse_url(server_url or ""), "headers": {"Authorization": f"Bearer {client_key}"}}
    return {"url": mcp_url(server_url or ""), "headers": {"Authorization": f"Bearer {client_key}"}}


def install_mcp_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path).expanduser().resolve()
    settings = require_client_settings(config_path)

    targets = args.target or ["all"]
    if "all" in targets:
        targets = list(_ALL_MCP_TARGETS)

    cwd = Path(args.cwd).resolve()

    for target in targets:
        if target == "codex":
            try:
                _install_codex_mcp(
                    sse_url(settings.get("server_url") or ""),
                    settings["client_api_key"],
                )
                print(f"Installed Minder MCP config for codex at {_global_target_path('codex')}")
            except Exception as e:
                print(f"Failed to install MCP for codex: {e}")
            continue

        try:
            if args.global_install:
                path = _global_target_path(target)
            else:
                path = local_target_path(target, cwd)
                
            payload = load_json(path)
            root_key = _target_root_key(target)
            if root_key not in payload:
                payload[root_key] = {}
                
            payload[root_key]["minder"] = _target_entry(
                target,
                settings["protocol"],
                settings["client_api_key"],
                settings.get("server_url"),
            )
            
            write_json(path, payload)
            print(f"Installed Minder MCP config for {target} at {path}")
        except Exception as e:
            print(f"Failed to install MCP for {target}: {e}")
            
    return 0


def uninstall_mcp_command(args: argparse.Namespace) -> int:
    targets = args.target or ["all"]
    if "all" in targets:
        targets = list(_ALL_MCP_TARGETS)

    cwd = Path(args.cwd).resolve()

    for target in targets:
        if target == "codex":
            try:
                removed = _uninstall_codex_mcp()
                if removed:
                    print(f"Removed Minder MCP config for codex from {_global_target_path('codex')}")
            except Exception as e:
                print(f"Failed to uninstall MCP for codex: {e}")
            continue

        try:
            if args.global_install:
                path = _global_target_path(target)
            else:
                path = local_target_path(target, cwd)
                
            if not path.is_file():
                continue
                
            payload = load_json(path)
            root_key = _target_root_key(target)
            if root_key in payload and "minder" in payload[root_key]:
                del payload[root_key]["minder"]
                if not payload[root_key]:
                    del payload[root_key]
                if not payload:
                    path.unlink(missing_ok=True)
                else:
                    write_json(path, payload)
                print(f"Removed Minder MCP config for {target} from {path}")
        except Exception as e:
            print(f"Failed to uninstall MCP for {target}: {e}")

    return 0


remove_mcp_command = uninstall_mcp_command
