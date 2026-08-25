from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_mcp_config(
    *,
    hub_url: str,
    client_key: str,
    workspace_name: str,
) -> dict[str, Any]:
    """Generates standard MCP Server JSON configuration for IDEs."""
    normalized_url = hub_url.rstrip("/")
    return {
        "mcpServers": {
            "minder": {
                "url": f"{normalized_url}/sse",
                "headers": {
                    "X-Minder-Client-Key": client_key,
                    "X-Minder-Workspace": workspace_name,
                },
            }
        }
    }


def write_ide_configs(
    *,
    project_dir: Path,
    hub_url: str,
    client_key: str,
    workspace_name: str,
) -> list[Path]:
    """Writes MCP configuration directly to .vscode/mcp.json and .cursor/mcp.json."""
    config_data = generate_mcp_config(
        hub_url=hub_url,
        client_key=client_key,
        workspace_name=workspace_name,
    )
    written_files: list[Path] = []

    # 1. VS Code (.vscode/mcp.json)
    vscode_dir = project_dir / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    vscode_file = vscode_dir / "mcp.json"
    with open(vscode_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    written_files.append(vscode_file)

    # 2. Cursor (.cursor/mcp.json)
    cursor_dir = project_dir / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    cursor_file = cursor_dir / "mcp.json"
    with open(cursor_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    written_files.append(cursor_file)

    return written_files
