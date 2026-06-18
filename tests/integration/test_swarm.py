from __future__ import annotations

import uuid

import pytest

from minder.application.swarm.service import ManifestNotApprovedError, SwarmService
from minder.config import MinderConfig
from minder.store.swarm import SwarmStore


@pytest.fixture
async def service(tmp_path):
    store = SwarmStore(db_path=str(tmp_path / "swarm.db"))
    await store.init_db()
    config = MinderConfig()
    config.swarm.heartbeat_ttl_seconds = 1
    config.swarm.failure_limit = 2
    yield SwarmService(store, config)
    await store.dispose()


@pytest.mark.asyncio
async def test_full_flow_create_plan_approve_claim_collect(service: SwarmService) -> None:
    # create
    sw = await service.create_swarm(goal="Refactor auth module")
    swarm_id = sw["swarm_id"]

    # plan — two tasks, second depends on first
    plan = await service.plan(
        swarm_id=swarm_id,
        tasks=[
            {"title": "scan", "runtime_hint": "claude"},
            {"title": "patch", "runtime_hint": "codex", "depends_on": [0]},
        ],
    )
    assert len(plan["tasks"]) == 2
    t_scan = plan["tasks"][0]["task_id"]
    t_patch = plan["tasks"][1]["task_id"]

    # Gate: spawning is blocked before approval (Q5)
    assert await service.can_spawn(swarm_id) is False
    with pytest.raises(ManifestNotApprovedError):
        await service.spawn_worker(
            swarm_id=swarm_id, task_id=t_scan, runtime="mock", prompt="x"
        )

    # propose → manifest lists workers, cost note flags paid runtime (codex)
    proposal = await service.propose(swarm_id=swarm_id)
    assert proposal["status"] == "pending_approval"
    assert len(proposal["workers"]) == 2
    assert "codex" in proposal["estimated_cost_note"]

    # approve → gate opens
    await service.approve(swarm_id=swarm_id, action="approve", approved_by="tester")
    assert await service.can_spawn(swarm_id) is True

    # spawn now works (mock runner)
    spawned = await service.spawn_worker(
        swarm_id=swarm_id, task_id=t_scan, runtime="mock", prompt="do scan"
    )
    assert spawned["runtime"] == "mock"

    # worker joins (presence)
    node = await service.join(swarm_id=swarm_id, runtime="mock", workspace="/repo")
    node_id = node["node_id"]

    # who → reflects presence + board
    who = await service.who(swarm_id=swarm_id)
    assert len(who["nodes"]) == 1
    assert len(who["tasks"]) == 2

    # Dependent task cannot be claimed before its dependency is done
    claim_patch = await service.claim(task_id=t_patch, node_id=node_id)
    assert claim_patch["claimed"] is False

    # Claim + complete the first task
    claim_scan = await service.claim(task_id=t_scan, node_id=node_id)
    assert claim_scan["claimed"] is True
    await service.report(
        task_id=t_scan,
        node_id=node_id,
        status="done",
        result_ref="memory:abc",
        summary="scanned",
        facts=["found 3 callsites"],
    )

    # Now the dependent task is unblocked → claimable
    claim_patch2 = await service.claim(task_id=t_patch, node_id=node_id)
    assert claim_patch2["claimed"] is True
    await service.report(task_id=t_patch, node_id=node_id, status="done", summary="patched")

    # collect → complete, handoffs present with artifact refs
    result = await service.collect(swarm_id=swarm_id)
    assert result["complete"] is True
    assert result["task_summary"]["done"] == 2
    assert any("memory:abc" in h["artifact_refs"] for h in result["handoffs"])


@pytest.mark.asyncio
async def test_atomic_claim_prevents_double_work(service: SwarmService) -> None:
    sw = await service.create_swarm(goal="g")
    swarm_id = sw["swarm_id"]
    plan = await service.plan(swarm_id=swarm_id, tasks=[{"title": "only"}])
    task_id = plan["tasks"][0]["task_id"]

    n1 = (await service.join(swarm_id=swarm_id, runtime="mock"))["node_id"]
    n2 = (await service.join(swarm_id=swarm_id, runtime="mock"))["node_id"]

    c1 = await service.claim(task_id=task_id, node_id=n1)
    c2 = await service.claim(task_id=task_id, node_id=n2)
    # Exactly one wins
    assert c1["claimed"] != c2["claimed"]


@pytest.mark.asyncio
async def test_failure_limit_auto_blocks(service: SwarmService) -> None:
    sw = await service.create_swarm(goal="g")
    swarm_id = sw["swarm_id"]
    plan = await service.plan(swarm_id=swarm_id, tasks=[{"title": "flaky"}])
    task_id = plan["tasks"][0]["task_id"]
    node_id = (await service.join(swarm_id=swarm_id, runtime="mock"))["node_id"]

    # First failure → back to ready
    await service.claim(task_id=task_id, node_id=node_id)
    r1 = await service.report(task_id=task_id, node_id=node_id, status="failed", summary="boom")
    assert r1["task_status"] == "failed"
    t = await service._store.get_task(uuid.UUID(task_id))
    assert t.status == "ready"

    # Second failure → auto-blocked (failure_limit=2)
    await service.claim(task_id=task_id, node_id=node_id)
    await service.report(task_id=task_id, node_id=node_id, status="failed", summary="boom2")
    t = await service._store.get_task(uuid.UUID(task_id))
    assert t.status == "blocked"


@pytest.mark.asyncio
async def test_dead_node_reaped_and_claim_released(service: SwarmService) -> None:
    import asyncio

    sw = await service.create_swarm(goal="g")
    swarm_id = sw["swarm_id"]
    plan = await service.plan(swarm_id=swarm_id, tasks=[{"title": "t"}])
    task_id = plan["tasks"][0]["task_id"]
    node_id = (await service.join(swarm_id=swarm_id, runtime="mock"))["node_id"]
    await service.claim(task_id=task_id, node_id=node_id)

    # heartbeat ttl is 1s in fixture — wait it out, then who() reaps + releases
    await asyncio.sleep(1.2)
    who = await service.who(swarm_id=swarm_id)
    dead = [n for n in who["nodes"] if n["status"] == "dead"]
    assert len(dead) == 1
    # released task is back to ready
    t = await service._store.get_task(uuid.UUID(task_id))
    assert t.status == "ready"
