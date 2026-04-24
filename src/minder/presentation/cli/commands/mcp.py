from __future__ import annotations

import argparse
import platform
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
    raise ValueError(f"Unknown global target: {target}")


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
        targets = list(_LOCAL_MCP_TARGETS)
        
    cwd = Path(args.cwd).resolve()
    
    for target in targets:
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
        targets = list(_LOCAL_MCP_TARGETS)
        
    cwd = Path(args.cwd).resolve()
    
    for target in targets:
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
