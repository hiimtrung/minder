"""ACP (Agent Client Protocol) runner — S-5.

Minder acts as an ACP *client* to drive any ACP-compatible agent through one
uniform interface (initialize → session/new → session/prompt → stream updates),
instead of bespoke code per vendor. See docs/roadmap/08 §3.4.

Transport: newline-delimited JSON-RPC 2.0 over the agent subprocess's stdio.
This is a minimal client covering the handshake, session creation (wiring the
Minder MCP server into the agent), prompting, and auto-approving tool permission
requests (the swarm already passed the human manifest gate, Q5).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from typing import Any

from minder.application.swarm.runners.base import RunnerHandle, RunnerStatus, _SubprocessRunner

logger = logging.getLogger(__name__)

ACP_PROTOCOL_VERSION = 1


class AcpClient:
    """Minimal ACP JSON-RPC client over a subprocess's stdio."""

    def __init__(self, command: list[str], cwd: str, env: dict[str, str] | None = None) -> None:
        self._command = command
        self._cwd = cwd
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._updates: list[dict[str, Any]] = []
        self._closed = asyncio.Event()

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            cwd=self._cwd,
            env={**os.environ, **(self._env or {})},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("ACP: non-JSON line: %r", line[:200])
                    continue
                await self._dispatch(msg)
        finally:
            self._closed.set()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("ACP agent closed"))

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        # Response to one of our requests
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(RuntimeError(f"ACP error: {msg['error']}"))
                else:
                    fut.set_result(msg["result"])
            return

        method = msg.get("method")
        # Request from the agent (has id) — we must respond.
        if "id" in msg:
            result = await self._handle_agent_request(method, msg.get("params") or {})
            await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
            return

        # Notification (no id) — e.g. session/update stream.
        if method == "session/update":
            self._updates.append(msg.get("params") or {})

    async def _handle_agent_request(self, method: str | None, params: dict[str, Any]) -> dict[str, Any]:
        # Auto-approve permission requests — human approval already happened at the
        # manifest gate (Q5). Pick the first "allow"-ish option offered.
        if method == "session/request_permission":
            options = params.get("options") or []
            chosen = None
            for opt in options:
                kind = str(opt.get("kind", "")).lower()
                name = str(opt.get("name", "")).lower()
                if "allow" in kind or "allow" in name or "yes" in name:
                    chosen = opt.get("optionId")
                    break
            if chosen is None and options:
                chosen = options[0].get("optionId")
            return {"outcome": {"outcome": "selected", "optionId": chosen}}
        # Unknown agent request — acknowledge minimally.
        return {}

    async def _send(self, msg: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self._proc.stdin.drain()

    async def _request(self, method: str, params: dict[str, Any], timeout: float = 120.0) -> Any:
        rid = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return await asyncio.wait_for(fut, timeout=timeout)

    async def initialize(self) -> dict[str, Any]:
        return await self._request(
            "initialize",
            {
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
            },
        )

    async def new_session(self, cwd: str, mcp_servers: list[dict[str, Any]]) -> str:
        result = await self._request("session/new", {"cwd": cwd, "mcpServers": mcp_servers})
        return result["sessionId"]

    async def prompt(self, session_id: str, text: str) -> str:
        result = await self._request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
            timeout=600.0,
        )
        return result.get("stopReason", "unknown")

    @property
    def updates(self) -> list[dict[str, Any]]:
        return self._updates

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
            except ProcessLookupError:
                pass
        if self._reader_task:
            self._reader_task.cancel()


class AcpRunner(_SubprocessRunner):
    """Drives an ACP-compatible agent. The agent binary is taken from
    ``MINDER_ACP_AGENT_CMD`` (shlex-split) or the constructor."""

    name = "acp"

    def __init__(self, agent_command: list[str] | None = None) -> None:
        if agent_command is None:
            raw = os.environ.get("MINDER_ACP_AGENT_CMD", "")
            agent_command = shlex.split(raw) if raw else []
        self._agent_command = agent_command

    def _mcp_servers_for_session(self, mcp_endpoint: str) -> list[dict[str, Any]]:
        return [{"name": "minder", "url": mcp_endpoint, "transport": "sse"}]

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
        if not self._agent_command:
            raise ValueError(
                "AcpRunner: no agent command. Set MINDER_ACP_AGENT_CMD or pass agent_command."
            )
        full_env = {**(env or {}), "MINDER_SWARM_ID": swarm_id, "MINDER_SWARM_TASK_ID": task_id}
        workdir = cwd or os.path.expanduser("~")
        client = AcpClient(self._agent_command, cwd=workdir, env=full_env)
        await client.start()
        await client.initialize()
        session_id = await client.new_session(workdir, self._mcp_servers_for_session(mcp_endpoint))

        async def _drive() -> None:
            try:
                await client.prompt(session_id, prompt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ACP prompt failed for task %s: %s", task_id, exc)
            finally:
                await client.close()

        drive_task = asyncio.create_task(_drive())
        return RunnerHandle(
            runtime=self.name,
            task_id=task_id,
            pid=client._proc.pid if client._proc else None,
            command=self._agent_command,
            extra={"_client": client, "_drive_task": drive_task, "session_id": session_id},
        )

    async def status(self, handle: RunnerHandle) -> RunnerStatus:
        drive_task = handle.extra.get("_drive_task")
        if drive_task is None:
            return RunnerStatus(running=False, detail="no drive task")
        return RunnerStatus(running=not drive_task.done())

    async def cancel(self, handle: RunnerHandle) -> None:
        client = handle.extra.get("_client")
        if client is not None:
            await client.close()
        drive_task = handle.extra.get("_drive_task")
        if drive_task is not None:
            drive_task.cancel()
