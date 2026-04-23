from __future__ import annotations

import argparse
from pathlib import Path

from ..utils.common import (
    upsert_managed_block,
    remove_managed_block,
)
from .mcp import install_mcp_command, uninstall_mcp_command, local_target_path

_IDE_GITIGNORE_KEY = "minder-ide-bootstrap"


def _ide_instruction_path(target: str, cwd: Path) -> Path | None:
    if target == "vscode":
        return cwd / ".github" / "copilot-instructions.md"
    if target == "cursor":
        return cwd / ".cursor" / "rules" / "minder.mdc"
    if target == "claude-code":
        return cwd / "CLAUDE.md"
    return None


def _ide_agent_path(target: str, cwd: Path) -> Path | None:
    if target in {"vscode", "cursor"}:
        return cwd / ".minder" / "agent.json"
    if target == "claude-code":
        return cwd / ".claude" / "agents" / "minder-repo-guide.md"
    return None


def _ide_bootstrap_instruction(target: str) -> str:
    return f"""# Minder IDE Bootstrap
This project is configured to use Minder.
- IDE: {target}
- Configuration managed by Minder CLI.
"""


def _ide_agent_content(target: str) -> str:
    return "{ \"name\": \"minder-agent\" }"


def install_ide_command(args: argparse.Namespace) -> int:
    # Ensure global_install is set for MCP command
    if not hasattr(args, "global_install"):
        setattr(args, "global_install", False)
    # First install MCP
    res = install_mcp_command(args)
    if res != 0:
        return res
        
    cwd = Path(args.cwd).resolve()
    targets = args.target or ["all"]
    if "all" in targets:
        targets = ["vscode", "cursor", "claude-code"]
        
    for target in targets:
        # Instruction
        path = _ide_instruction_path(target, cwd)
        if path:
            body = _ide_bootstrap_instruction(target)
            # Add header for instructions
            body = "# Minder repo-local instructions\n" + body
            upsert_managed_block(
                path,
                f"minder-ide-instructions:{target}",
                body,
            )
            
        # Agent
        path = _ide_agent_path(target, cwd)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = _ide_agent_content(target)
            if path.suffix == ".md":
                # Special content for agents
                content = _ide_bootstrap_instruction(target)
                if "minder-repo-guide" in path.name:
                    content = "# minder-repo-guide\n" + content
            path.write_text(content, encoding="utf-8")
            
    # Update gitignore
    gitignore = cwd / ".gitignore"
    ignore_lines = ".minder/current\n.minder/releases\n"
    for target in targets:
        path = local_target_path(target, cwd)
        if path:
            # Relative path to cwd
            try:
                rel_path = path.relative_to(cwd)
                ignore_lines += f"{rel_path}\n"
            except Exception:
                pass
    upsert_managed_block(gitignore, _IDE_GITIGNORE_KEY, ignore_lines)
    
    # Metadata
    metadata_path = cwd / ".minder" / "ide-bootstrap.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    from ..utils.common import write_json
    write_json(metadata_path, {"targets": targets, "version": "1.0.0"})
    
    print(f"Installed Minder IDE asset in {cwd}")
    return 0


def uninstall_ide_command(args: argparse.Namespace) -> int:
    # Ensure global_install is set for MCP command
    if not hasattr(args, "global_install"):
        setattr(args, "global_install", False)
    # First uninstall MCP
    res = uninstall_mcp_command(args)
    
    cwd = Path(args.cwd).resolve()
    targets = args.target or ["all"]
    if "all" in targets:
        targets = ["vscode", "cursor", "claude-code"]
        
    # Remove assets...
    for target in targets:
        path = _ide_instruction_path(target, cwd)
        if path:
            remove_managed_block(path, f"minder-ide-instructions:{target}")
        path = _ide_agent_path(target, cwd)
        if path and path.is_file():
            path.unlink()
            # Try to remove empty parent
            try:
                path.parent.rmdir()
            except Exception:
                pass
            
    gitignore = cwd / ".gitignore"
    remove_managed_block(gitignore, _IDE_GITIGNORE_KEY)
    
    metadata_path = cwd / ".minder" / "ide-bootstrap.json"
    if metadata_path.is_file():
        metadata_path.unlink()
        try:
            metadata_path.parent.rmdir()
        except Exception:
            pass
            
    print(f"Removed Minder IDE asset from {cwd}")
    return res
