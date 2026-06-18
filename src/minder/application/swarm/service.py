"""Swarm coordination service — the blackboard logic.

Implements the substrate from docs/roadmap/08-swarm-coordination-substrate.md:
presence (R3), board + atomic claim, structured handoff (R4), and the mandatory
human-approval gate (Q5) that blocks spawning until a manifest is approved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from minder.config import MinderConfig
from minder.domain.entities.swarm import default_worker_spec
from minder.store.swarm import SwarmStore


class ManifestNotApprovedError(Exception):
    """Raised when a spawn is attempted before the swarm manifest is approved (Q5)."""


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class SwarmService:
    def __init__(self, swarm_store: SwarmStore, config: MinderConfig) -> None:
        self._store = swarm_store
        self._config = config

    # ── Orchestrator: create / plan ─────────────────────────────────────────
    async def create_swarm(self, *, goal: str, workflow_id: str | None = None) -> dict[str, Any]:
        swarm = await self._store.create_swarm(goal=goal, workflow_id=_uuid(workflow_id))
        return {
            "swarm_id": str(swarm.id),
            "status": swarm.status,
            "goal": swarm.goal,
            "_next_steps": [
                "Call minder_swarm_plan(swarm_id, tasks=[...]) to break the goal into board tasks.",
                "Then minder_swarm_propose(swarm_id) to generate a manifest for human approval.",
            ],
        }

    async def plan(self, *, swarm_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Expand a goal/workflow into board tasks. ``tasks`` items accept:
        title, description, runtime_hint, depends_on (list of indices or task ids)."""
        sid = _uuid(swarm_id)
        created: list[dict[str, Any]] = []
        index_to_id: dict[int, str] = {}

        # First pass — create tasks without deps so we can resolve index refs.
        for i, spec in enumerate(tasks):
            t = await self._store.create_task(
                swarm_id=sid,
                title=spec.get("title", f"task-{i}"),
                description=spec.get("description", ""),
                runtime_hint=spec.get("runtime_hint"),
                workflow_id=_uuid(spec.get("workflow_id")),
            )
            index_to_id[i] = str(t.id)
            created.append({"index": i, "task_id": str(t.id), "title": t.title})

        # Second pass — resolve depends_on (allow integer indices or explicit ids).
        for i, spec in enumerate(tasks):
            deps_raw = spec.get("depends_on") or []
            resolved: list[str] = []
            for d in deps_raw:
                if isinstance(d, int) and d in index_to_id:
                    resolved.append(index_to_id[d])
                else:
                    resolved.append(str(d))
            status = "blocked" if resolved else "ready"
            await self._store.update_task(_uuid(index_to_id[i]), depends_on=resolved, status=status)

        await self._store.update_swarm(sid, status="planning")
        return {"swarm_id": swarm_id, "tasks": created, "_next_steps": ["minder_swarm_propose(swarm_id)"]}

    # ── Approval gate (Q5) ──────────────────────────────────────────────────
    async def propose(self, *, swarm_id: str) -> dict[str, Any]:
        """Build a Swarm Manifest (one worker spec per distinct runtime/task group)
        and park it at status ``pending_approval`` for a human to review/edit."""
        sid = _uuid(swarm_id)
        swarm = await self._store.get_swarm(sid)
        if swarm is None:
            raise ValueError(f"swarm not found: {swarm_id}")
        tasks = await self._store.list_tasks(sid)

        workers: list[dict[str, Any]] = []
        paid_runtimes: list[str] = []
        for t in tasks:
            spec = default_worker_spec()
            runtime = t.runtime_hint or "claude"
            spec.update(
                {
                    "label": t.title[:40],
                    "runtime": runtime,
                    "function": t.description or t.title,
                    "task_ids": [str(t.id)],
                    "workspace": "",
                }
            )
            workers.append(spec)
            if runtime in {"codex", "antigravity"} and runtime not in paid_runtimes:
                paid_runtimes.append(runtime)

        cost_note = (
            f"Paid/cloud runtimes in this plan: {', '.join(paid_runtimes)}."
            if paid_runtimes
            else "All workers use local/included runtimes."
        )
        manifest = await self._store.create_manifest(
            swarm_id=sid,
            goal=swarm.goal,
            workflow_id=swarm.workflow_id,
            status="pending_approval",
            workers=workers,
            estimated_cost_note=cost_note,
        )
        await self._store.update_swarm(sid, status="pending_approval")
        return {
            "manifest_id": str(manifest.id),
            "swarm_id": swarm_id,
            "status": manifest.status,
            "workers": workers,
            "estimated_cost_note": cost_note,
            "_next_steps": [
                "A human must call minder_swarm_approve(swarm_id, action='approve'|'edit'|'reject').",
                "Spawning is BLOCKED until the manifest is approved.",
            ],
        }

    async def approve(
        self,
        *,
        swarm_id: str,
        action: str,
        approved_by: str | None = None,
        workers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        sid = _uuid(swarm_id)
        manifest = await self._store.get_manifest_for_swarm(sid)
        if manifest is None:
            raise ValueError("no manifest to approve; call minder_swarm_propose first")

        if action == "approve":
            updated = await self._store.update_manifest(
                manifest.id,
                status="approved",
                approved_by=approved_by or "human",
                approved_at=datetime.now(UTC),
            )
            await self._store.update_swarm(sid, status="approved")
        elif action == "edit":
            updated = await self._store.update_manifest(
                manifest.id,
                workers=workers if workers is not None else manifest.workers,
                status="approved",
                approved_by=approved_by or "human",
                approved_at=datetime.now(UTC),
            )
            await self._store.update_swarm(sid, status="approved")
        elif action == "reject":
            updated = await self._store.update_manifest(manifest.id, status="rejected")
            await self._store.update_swarm(sid, status="planning")
        else:
            raise ValueError(f"unknown action: {action}")

        return {"swarm_id": swarm_id, "manifest_status": updated.status if updated else None}

    async def can_spawn(self, swarm_id: str) -> bool:
        """Gate check (Q5). Spawning is allowed only when a manifest is approved."""
        if not self._config.swarm.require_manifest_approval:
            return True
        manifest = await self._store.get_manifest_for_swarm(_uuid(swarm_id))
        return manifest is not None and manifest.status == "approved"

    async def assert_can_spawn(self, swarm_id: str) -> None:
        if not await self.can_spawn(swarm_id):
            raise ManifestNotApprovedError(
                f"swarm {swarm_id}: manifest not approved — propose + human approval required before spawning"
            )

    async def spawn_worker(
        self,
        *,
        swarm_id: str,
        task_id: str,
        runtime: str,
        prompt: str,
        cwd: str = "",
        mcp_endpoint: str = "",
    ) -> dict[str, Any]:
        """Launch a heterogeneous worker (S-3). Hard-gated by manifest approval (Q5).

        The gate lives here (runner layer), not just the UI, so even a plain script
        orchestrator cannot bypass human approval.
        """
        await self.assert_can_spawn(swarm_id)
        from minder.application.swarm.runners import create_runner

        runner = create_runner(runtime)
        handle = await runner.spawn(
            task_id=task_id,
            swarm_id=swarm_id,
            mcp_endpoint=mcp_endpoint,
            prompt=prompt,
            cwd=cwd,
        )
        return {
            "runtime": runtime,
            "task_id": task_id,
            "pid": handle.pid,
            "command": handle.command,
        }

    # ── Worker: presence + board ────────────────────────────────────────────
    async def join(
        self,
        *,
        swarm_id: str,
        runtime: str,
        role: str = "worker",
        workspace: str = "",
        session_id: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        node = await self._store.create_node(
            swarm_id=_uuid(swarm_id),
            runtime=runtime,
            role=role,
            workspace=workspace,
            session_id=_uuid(session_id),
            capabilities=capabilities or [],
            status="idle",
        )
        return {
            "node_id": str(node.id),
            "swarm_id": swarm_id,
            "_next_steps": [
                "minder_swarm_who(swarm_id) to see who else is active before acting.",
                "minder_swarm_claim(task_id, node_id) to claim a ready task.",
                "Send minder_swarm_heartbeat(node_id) regularly so you aren't reaped as dead.",
            ],
        }

    async def heartbeat(self, *, node_id: str, status: str | None = None) -> dict[str, Any]:
        node = await self._store.heartbeat(_uuid(node_id), status=status)
        return {"node_id": node_id, "status": node.status if node else "unknown"}

    async def who(self, *, swarm_id: str) -> dict[str, Any]:
        """The anti-hallucination read: ai đang làm gì, ở đâu, trạng thái nào."""
        sid = _uuid(swarm_id)
        # Reap dead nodes first so the snapshot reflects reality, then release their claims.
        released = await self._store.reap_dead_nodes(sid, self._config.swarm.heartbeat_ttl_seconds)
        for task_id in released:
            await self._store.release_task(task_id)

        nodes = await self._store.list_nodes(sid)
        tasks = await self._store.list_tasks(sid)
        return {
            "swarm_id": swarm_id,
            "nodes": [
                {
                    "node_id": str(n.id),
                    "runtime": n.runtime,
                    "role": n.role,
                    "status": n.status,
                    "workspace": n.workspace,
                    "current_task_id": str(n.current_task_id) if n.current_task_id else None,
                }
                for n in nodes
            ],
            "tasks": [
                {
                    "task_id": str(t.id),
                    "title": t.title,
                    "status": t.status,
                    "assignee_node_id": str(t.assignee_node_id) if t.assignee_node_id else None,
                    "depends_on": t.depends_on,
                }
                for t in tasks
            ],
        }

    async def claim(self, *, task_id: str, node_id: str) -> dict[str, Any]:
        """Atomic claim, gated by DAG dependencies (deps must be ``done``)."""
        tid = _uuid(task_id)
        task = await self._store.get_task(tid)
        if task is None:
            raise ValueError(f"task not found: {task_id}")

        # Dependency gate — cannot claim until every dependency is done.
        if task.depends_on:
            sid = task.swarm_id
            all_tasks = {str(t.id): t for t in await self._store.list_tasks(sid)}
            for dep in task.depends_on:
                dep_t = all_tasks.get(str(dep))
                if dep_t is None or dep_t.status != "done":
                    return {"claimed": False, "reason": f"dependency {dep} not done yet"}

        claimed = await self._store.claim_task(
            tid, _uuid(node_id), self._config.swarm.claim_ttl_seconds
        )
        if claimed is None:
            return {"claimed": False, "reason": "task already claimed or not ready"}

        await self._store.update_task(tid, status="in_progress")
        await self._store.update_node(_uuid(node_id), current_task_id=tid, status="working")
        return {"claimed": True, "task_id": task_id, "title": claimed.title}

    async def report(
        self,
        *,
        task_id: str,
        node_id: str,
        status: str = "done",
        result_ref: str | None = None,
        summary: str = "",
        artifact_refs: list[str] | None = None,
        facts: list[str] | None = None,
        to_task_id: str | None = None,
    ) -> dict[str, Any]:
        """Worker reports completion. Worker has ALREADY written results straight to
        the operational store (Q4); this records a lightweight pointer Handoff and
        advances the board. After ``failure_limit`` failures a task is auto-blocked."""
        tid = _uuid(task_id)
        task = await self._store.get_task(tid)
        if task is None:
            raise ValueError(f"task not found: {task_id}")

        if status == "done":
            await self._store.update_task(tid, status="done", result_ref=result_ref)
            await self._store.update_node(_uuid(node_id), current_task_id=None, status="idle")
            await self._unblock_dependents(task.swarm_id, str(tid))
        else:  # failed
            attempts = task.attempts + 1
            new_status = "blocked" if attempts >= self._config.swarm.failure_limit else "ready"
            await self._store.update_task(
                tid,
                status=new_status,
                attempts=attempts,
                assignee_node_id=None,
                claim_expires_at=None,
                block_reason=(summary or "repeated failures") if new_status == "blocked" else None,
            )
            await self._store.update_node(_uuid(node_id), current_task_id=None, status="idle")

        handoff = await self._store.create_handoff(
            swarm_id=task.swarm_id,
            from_task_id=tid,
            to_task_id=_uuid(to_task_id),
            from_node_id=_uuid(node_id),
            summary=summary,
            artifact_refs=artifact_refs or ([result_ref] if result_ref else []),
            facts=facts or [],
        )
        return {"task_id": task_id, "task_status": status, "handoff_id": str(handoff.id)}

    async def _unblock_dependents(self, swarm_id: uuid.UUID, done_task_id: str) -> None:
        """When a task finishes, promote blocked tasks whose deps are now all done."""
        tasks = await self._store.list_tasks(swarm_id)
        by_id = {str(t.id): t for t in tasks}
        for t in tasks:
            if t.status != "blocked" or not t.depends_on:
                continue
            if all(by_id.get(str(d)) and by_id[str(d)].status == "done" for d in t.depends_on):
                await self._store.update_task(t.id, status="ready")

    async def block(self, *, task_id: str, reason: str) -> dict[str, Any]:
        await self._store.update_task(_uuid(task_id), status="blocked", block_reason=reason)
        return {"task_id": task_id, "status": "blocked", "reason": reason}

    async def collect(self, *, swarm_id: str) -> dict[str, Any]:
        """Aggregate the swarm's outcome — handoffs + task statuses (closes the loop)."""
        sid = _uuid(swarm_id)
        tasks = await self._store.list_tasks(sid)
        handoffs = await self._store.list_handoffs(sid)
        done = [t for t in tasks if t.status == "done"]
        all_done = bool(tasks) and len(done) == len(tasks)
        if all_done:
            await self._store.update_swarm(sid, status="done", finished_at=datetime.now(UTC))

        return {
            "swarm_id": swarm_id,
            "complete": all_done,
            "task_summary": {
                "total": len(tasks),
                "done": len(done),
                "blocked": len([t for t in tasks if t.status == "blocked"]),
                "in_progress": len([t for t in tasks if t.status == "in_progress"]),
            },
            "handoffs": [
                {
                    "from_task_id": str(h.from_task_id) if h.from_task_id else None,
                    "summary": h.summary,
                    "artifact_refs": h.artifact_refs,
                    "facts": h.facts,
                }
                for h in handoffs
            ],
        }
