"""Agent runner adapters (decision R2 / S-3).

Each runtime (Claude Code, Codex, …) is a thin adapter that knows how to launch
that vendor's CLI with an MCP config pointing back at Minder plus a task context.
Adding a new runtime = adding ~one adapter, nothing else changes.

The actual spawn is gated upstream by SwarmService.assert_can_spawn (Q5).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class RunnerHandle:
    runtime: str
    task_id: str
    pid: int | None = None
    command: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunnerStatus:
    running: bool
    exit_code: int | None = None
    detail: str = ""


@runtime_checkable
class AgentRunner(Protocol):
    name: str

    async def spawn(
        self,
        *,
        task_id: str,
        swarm_id: str,
        mcp_endpoint: str,
        prompt: str,
        cwd: str,
        env: dict[str, str] | None = None,
    ) -> RunnerHandle: ...

    async def status(self, handle: RunnerHandle) -> RunnerStatus: ...

    async def cancel(self, handle: RunnerHandle) -> None: ...


class _SubprocessRunner:
    """Shared base — writes an MCP config file and launches a CLI subprocess."""

    name = "subprocess"

    def _mcp_config_payload(self, mcp_endpoint: str) -> dict[str, Any]:
        # Minder runs as an MCP server; the spawned agent connects as a client.
        return {"mcpServers": {"minder": {"url": mcp_endpoint, "transport": "sse"}}}

    def _write_mcp_config(self, mcp_endpoint: str) -> str:
        payload = self._mcp_config_payload(mcp_endpoint)
        fd, path = tempfile.mkstemp(prefix=f"minder-mcp-{self.name}-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        return path

    def _build_command(self, *, mcp_config_path: str, prompt: str) -> list[str]:
        raise NotImplementedError

    async def spawn(
        self,
        *,
        task_id: str,
        swarm_id: str,
        mcp_endpoint: str,
        prompt: str,
        cwd: str,
        env: dict[str, str] | None = None,
    ) -> RunnerHandle:
        import asyncio

        mcp_config_path = self._write_mcp_config(mcp_endpoint)
        command = self._build_command(mcp_config_path=mcp_config_path, prompt=prompt)
        full_env = {**os.environ, **(env or {})}
        full_env["MINDER_SWARM_ID"] = swarm_id
        full_env["MINDER_SWARM_TASK_ID"] = task_id
        workdir = cwd or str(Path.home())

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=workdir,
            env=full_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return RunnerHandle(
            runtime=self.name,
            task_id=task_id,
            pid=proc.pid,
            command=command,
            extra={"mcp_config_path": mcp_config_path, "_proc": proc},
        )

    async def status(self, handle: RunnerHandle) -> RunnerStatus:
        proc = handle.extra.get("_proc")
        if proc is None:
            return RunnerStatus(running=False, detail="no process handle")
        if proc.returncode is None:
            return RunnerStatus(running=True)
        return RunnerStatus(running=False, exit_code=proc.returncode)

    async def cancel(self, handle: RunnerHandle) -> None:
        proc = handle.extra.get("_proc")
        if proc is not None and proc.returncode is None:
            proc.terminate()


class MockRunner(_SubprocessRunner):
    """No-op runner for tests / dry environments — records the would-be command."""

    name = "mock"

    async def spawn(
        self,
        *,
        task_id: str,
        swarm_id: str,
        mcp_endpoint: str,
        prompt: str,
        cwd: str,
        env: dict[str, str] | None = None,
    ) -> RunnerHandle:
        return RunnerHandle(
            runtime=self.name,
            task_id=task_id,
            pid=None,
            command=["<mock>", prompt[:40]],
            extra={"mcp_endpoint": mcp_endpoint, "swarm_id": swarm_id, "cwd": cwd},
        )

    async def status(self, handle: RunnerHandle) -> RunnerStatus:
        return RunnerStatus(running=False, exit_code=0, detail="mock")

    async def cancel(self, handle: RunnerHandle) -> None:
        return None
