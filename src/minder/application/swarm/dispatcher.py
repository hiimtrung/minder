"""Swarm dispatcher (S-4) — Minder-spawn model.

A long-lived background loop that sweeps the board and, for ready tasks carrying a
``runtime_hint``, launches the matching worker via the runner registry. Mirrors the
Hermes Kanban dispatcher invariants: reclaim stale claims, promote ready tasks,
respect the approval gate (Q5), cap concurrency, and back off after repeated
failures (failure_limit handled in SwarmService.report).

Off by default (config.swarm.dispatcher_enabled = False) — pull-spawn is the
primary path first (decision Q1). Enable when you want hands-off orchestration.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from minder.application.swarm.service import ManifestNotApprovedError, SwarmService
from minder.config import MinderConfig
from minder.store.swarm import SwarmStore

logger = logging.getLogger(__name__)


class SwarmDispatcher:
    def __init__(self, store: SwarmStore, service: SwarmService, config: MinderConfig) -> None:
        self._store = store
        self._service = service
        self._config = config
        self._task: asyncio.Task | None = None
        self._shutdown = asyncio.Event()
        # task_id -> last spawn time, to avoid re-spawning a task every tick.
        self._spawn_cooldown: dict[str, datetime] = {}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._shutdown.clear()
            self._task = asyncio.create_task(self._loop())
            logger.info("SwarmDispatcher started (tick=%ss)", self._config.swarm.dispatcher_tick_seconds)

    async def stop(self) -> None:
        self._shutdown.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.sleep(self._config.swarm.dispatcher_tick_seconds)
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # never let the loop die
                logger.error("SwarmDispatcher tick error: %s", exc, exc_info=True)

    async def tick(self) -> dict[str, Any]:
        """One sweep. Returns a small report (also handy for tests / observability)."""
        spawned: list[dict[str, Any]] = []
        reclaimed_tasks = 0

        swarms = await self._store.list_swarms()
        for swarm in swarms:
            if swarm.status in {"done", "failed"}:
                continue

            # 1. Reclaim: reap dead nodes and release their claims so work isn't stranded.
            released = await self._store.reap_dead_nodes(
                swarm.id, self._config.swarm.heartbeat_ttl_seconds
            )
            for task_id in released:
                await self._store.release_task(task_id)
                reclaimed_tasks += 1

            # 2. Gate (Q5): only dispatch for swarms whose manifest is approved.
            if not await self._service.can_spawn(str(swarm.id)):
                continue

            # 3. Spawn workers for ready, unassigned, runtime-hinted tasks (capped).
            budget = self._config.swarm.max_concurrent_spawns
            for task in await self._store.list_tasks(swarm.id):
                if budget <= 0:
                    break
                if task.status != "ready" or not task.runtime_hint:
                    continue
                if task.attempts >= self._config.swarm.failure_limit:
                    continue
                if self._on_cooldown(str(task.id)):
                    continue

                try:
                    result = await self._service.spawn_worker(
                        swarm_id=str(swarm.id),
                        task_id=str(task.id),
                        runtime=task.runtime_hint,
                        prompt=self._build_worker_prompt(swarm.goal, task.title, task.description, str(swarm.id), str(task.id)),
                        mcp_endpoint=self._mcp_endpoint(),
                    )
                    self._spawn_cooldown[str(task.id)] = datetime.now(UTC)
                    spawned.append(result)
                    budget -= 1
                except ManifestNotApprovedError:
                    break  # gate closed mid-sweep; stop dispatching this swarm
                except Exception as exc:
                    logger.warning("dispatch spawn failed for task %s: %s", task.id, exc)

            if swarm.status == "approved":
                await self._store.update_swarm(swarm.id, status="running")

        return {"spawned": spawned, "reclaimed_tasks": reclaimed_tasks}

    def _on_cooldown(self, task_id: str) -> bool:
        last = self._spawn_cooldown.get(task_id)
        if last is None:
            return False
        age = (datetime.now(UTC) - last).total_seconds()
        return age < self._config.swarm.claim_ttl_seconds

    def _mcp_endpoint(self) -> str:
        if self._config.swarm.mcp_endpoint:
            return self._config.swarm.mcp_endpoint
        host = self._config.server.host
        port = self._config.server.port
        return f"http://{host}:{port}/sse"

    @staticmethod
    def _build_worker_prompt(goal: str, title: str, description: str, swarm_id: str, task_id: str) -> str:
        return (
            "You are a worker in a Minder agent swarm. Connect to the Minder MCP server.\n"
            f"Swarm goal: {goal}\n"
            f"Your task ({task_id}): {title}\n{description}\n\n"
            "Procedure:\n"
            f"1. minder_swarm_join(swarm_id='{swarm_id}', runtime=<your runtime>, workspace=<cwd>) → node_id\n"
            "2. minder_swarm_who(swarm_id) — read who else is active before acting (avoid duplicate work)\n"
            f"3. minder_swarm_claim(task_id='{task_id}', node_id=...) — only proceed if claimed=true\n"
            "4. Do the work. Write results to the operational store (memory/graph/document).\n"
            "5. minder_swarm_report(task_id, node_id, status='done', result_ref=..., facts=[...]).\n"
            "Send minder_swarm_heartbeat periodically so you aren't reaped as dead."
        )
