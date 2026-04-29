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
        # User scope: ~/.claude.json stores cross-project MCP servers under top-level mcpServers key
        return Path.home() / ".claude.json"
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
        # Project scope: .mcp.json at project root, shared via version control
        return cwd / ".mcp.json"
    if target == "antigravity":
        del cwd
        return Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    raise ValueError(f"Unknown local target: {target}")


def _target_root_key(target: str) -> str:
    if target == "vscode":
        return "servers"
    return "mcpServers"


def _ensure_gitignored(cwd: Path, filename: str) -> None:
    gitignore = cwd / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    for line in existing.splitlines():
        if line.strip() in (filename, f"/{filename}"):
            return
    sep = "" if not existing or existing.endswith("\n") else "\n"
    gitignore.write_text(existing + sep + filename + "\n", encoding="utf-8")
    print(f"  Added '{filename}' to .gitignore")


def _remove_gitignored(cwd: Path, filename: str) -> None:
    gitignore = cwd / ".gitignore"
    if not gitignore.is_file():
        return
    lines = gitignore.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [line for line in lines if line.strip() not in (filename, f"/{filename}")]
    if len(filtered) < len(lines):
        gitignore.write_text("".join(filtered), encoding="utf-8")


def _remote_url(protocol: str, server_url: str) -> str:
    return sse_url(server_url) if protocol == "sse" else mcp_url(server_url)


def _target_entry(
    target: str,
    protocol: str,
    client_key: str,
    server_url: str | None,
) -> dict[str, Any]:
    if protocol == "stdio":
        entry: dict[str, Any] = {
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

    # Remote transport: URL and auth header are uniform across all targets.
    # Only format differences below (key name, type field) per IDE spec.
    url = _remote_url(protocol, server_url or "")
    headers = {"X-Minder-Client-Key": client_key}

    if target == "antigravity":
        # Gemini CLI expects "serverUrl" instead of "url"
        return {"serverUrl": url, "headers": headers}
    if target in ("vscode", "claude-code"):
        # VSCode and Claude Code require an explicit "type" field
        return {"type": protocol, "url": url, "headers": headers}

    # Standard format: cursor and all future targets
    return {"url": url, "headers": headers}


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
            path = _global_target_path(target) if args.global_install else local_target_path(target, cwd)
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

            if not args.global_install and target == "claude-code":
                _ensure_gitignored(cwd, ".mcp.json")
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

            if not args.global_install and target == "claude-code":
                _remove_gitignored(cwd, ".mcp.json")
        except Exception as e:
            print(f"Failed to uninstall MCP for {target}: {e}")

    return 0


remove_mcp_command = uninstall_mcp_command
