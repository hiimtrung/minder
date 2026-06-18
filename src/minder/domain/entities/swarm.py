"""Swarm coordination domain schemas (see docs/roadmap/08-swarm-coordination-substrate.md).

These back the *coordination* state (presence, board, manifest) that lives in a
dedicated ``swarm.db`` — separate from the operational store so high-frequency
heartbeat writes never contend with graph/memory queries (decision Q3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from minder.domain.entities.base import BaseModelMeta


# Swarm lifecycle: planning → pending_approval → approved → running → done/failed
class SwarmSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    goal: str
    workflow_id: uuid.UUID | None = None
    status: str = "planning"
    created_at: datetime | None = None
    finished_at: datetime | None = None


# Presence registry — "ai đang làm gì, ở đâu, trạng thái nào" (R3)
class SwarmNodeSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    swarm_id: uuid.UUID
    runtime: str  # "claude" | "codex" | "gemini" | "antigravity" | ...
    role: str = "worker"  # "orchestrator" | "worker"
    session_id: uuid.UUID | None = None
    current_task_id: uuid.UUID | None = None
    status: str = "idle"  # idle | working | blocked | done | dead
    workspace: str = ""  # cwd / repo path — "ở ĐÂU"
    capabilities: list[str] = Field(default_factory=list)
    last_heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


# Board / work queue
class SwarmTaskSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    swarm_id: uuid.UUID
    title: str
    description: str = ""
    workflow_id: uuid.UUID | None = None
    status: str = "ready"  # ready | claimed | in_progress | blocked | done | failed
    assignee_node_id: uuid.UUID | None = None
    runtime_hint: str | None = None
    depends_on: list[str] = Field(default_factory=list)  # task ids (DAG)
    claim_expires_at: datetime | None = None
    result_ref: str | None = None
    attempts: int = 0
    block_reason: str | None = None
    created_at: datetime | None = None


# Structured handoff — CON TRỎ, not a store (decision Q4: workers write straight
# to the operational store; the handoff just points other nodes at the truth).
class HandoffSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    swarm_id: uuid.UUID
    from_task_id: uuid.UUID | None = None
    to_task_id: uuid.UUID | None = None
    from_node_id: uuid.UUID | None = None
    summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


# Human-approval gate (decision Q5). A swarm cannot spawn any worker until its
# manifest reaches status == "approved". ``workers`` is a list of WorkerSpec dicts.
class SwarmManifestSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    swarm_id: uuid.UUID
    goal: str = ""
    workflow_id: uuid.UUID | None = None
    status: str = "pending_approval"  # pending_approval | approved | rejected
    workers: list[dict[str, Any]] = Field(default_factory=list)  # WorkerSpec dicts
    estimated_cost_note: str = ""
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None


def default_worker_spec() -> dict[str, Any]:
    """Shape of a single WorkerSpec entry inside a manifest (for reference/UI)."""
    return {
        "label": "",
        "runtime": "claude",
        "role": "worker",
        "function": "",
        "task_ids": [],
        "workspace": "",
        "toolsets": [],
        "max_iterations": 30,
        "budget": None,
        "editable": True,
    }
