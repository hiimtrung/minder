"""Concrete vendor runners — Claude Code and Codex (S-3).

Both connect to Minder over MCP (Minder = MCP server). The commands below match
each CLI's headless/non-interactive invocation; the exact flags may need tuning
per CLI version (see docs/guides/swarm-setup-claude-antigravity.md, produced after
implementation per decision Q2).
"""

from __future__ import annotations

from minder.application.swarm.runners.base import _SubprocessRunner


class ClaudeRunner(_SubprocessRunner):
    name = "claude"

    def _build_command(self, *, mcp_config_path: str, prompt: str) -> list[str]:
        # Claude Code headless: run a single prompt, wire MCP via config file.
        return [
            "claude",
            "-p",
            prompt,
            "--mcp-config",
            mcp_config_path,
            "--permission-mode",
            "acceptEdits",
        ]


class CodexRunner(_SubprocessRunner):
    name = "codex"

    def _build_command(self, *, mcp_config_path: str, prompt: str) -> list[str]:
        # Codex exec (non-interactive). MCP servers are configured via Codex's own
        # config; we pass the generated config path through an env-pointer the
        # wrapper reads. Kept explicit so the command is inspectable in the manifest.
        return [
            "codex",
            "exec",
            "--mcp-config",
            mcp_config_path,
            prompt,
        ]


class AntigravityRunner(_SubprocessRunner):
    name = "antigravity"

    def _build_command(self, *, mcp_config_path: str, prompt: str) -> list[str]:
        # Placeholder invocation — Antigravity is an agentic IDE; headless support
        # and exact CLI entrypoint to be confirmed during S-5 (ACP path preferred).
        return [
            "antigravity",
            "agent",
            "--mcp-config",
            mcp_config_path,
            "--prompt",
            prompt,
        ]
