from __future__ import annotations

import sys
from pathlib import Path

import pytest

from minder.application.swarm.dispatcher import SwarmDispatcher
from minder.application.swarm.runners.acp import AcpClient, AcpRunner
from minder.application.swarm.service import SwarmService
from minder.config import MinderConfig
from minder.store.swarm import SwarmStore

_MOCK_AGENT = str(Path(__file__).parent / "_acp_mock_agent.py")


@pytest.fixture
async def swarm(tmp_path):
    store = SwarmStore(db_path=str(tmp_path / "swarm.db"))
    await store.init_db()
    config = MinderConfig()
    config.swarm.max_concurrent_spawns = 5
    yield store, SwarmService(store, config), config
    await store.dispose()


# ── S-4 dispatcher ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dispatcher_respects_gate_then_spawns(swarm) -> None:
    store, service, config = swarm
    dispatcher = SwarmDispatcher(store, service, config)

    sw = await service.create_swarm(goal="build")
    swarm_id = sw["swarm_id"]
    await service.plan(
        swarm_id=swarm_id,
        tasks=[{"title": "a", "runtime_hint": "mock"}, {"title": "b", "runtime_hint": "mock"}],
    )

    # Gate closed → dispatcher spawns nothing
    report1 = await dispatcher.tick()
    assert report1["spawned"] == []

    # Approve → dispatcher spawns workers for ready, runtime-hinted tasks
    await service.propose(swarm_id=swarm_id)
    await service.approve(swarm_id=swarm_id, action="approve")
    report2 = await dispatcher.tick()
    assert len(report2["spawned"]) == 2

    # Cooldown prevents immediate re-spawn on the next tick
    report3 = await dispatcher.tick()
    assert report3["spawned"] == []


@pytest.mark.asyncio
async def test_dispatcher_skips_tasks_without_runtime_hint(swarm) -> None:
    store, service, config = swarm
    dispatcher = SwarmDispatcher(store, service, config)
    sw = await service.create_swarm(goal="g")
    swarm_id = sw["swarm_id"]
    await service.plan(swarm_id=swarm_id, tasks=[{"title": "manual"}])  # no runtime_hint
    await service.propose(swarm_id=swarm_id)
    await service.approve(swarm_id=swarm_id, action="approve")
    report = await dispatcher.tick()
    assert report["spawned"] == []


# ── S-5 ACP ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_acp_client_handshake_and_prompt() -> None:
    client = AcpClient([sys.executable, _MOCK_AGENT], cwd=".")
    await client.start()
    init = await client.initialize()
    assert init["protocolVersion"] == 1
    session_id = await client.new_session(".", [{"name": "minder", "url": "http://x/sse"}])
    assert session_id == "sess-mock-1"
    stop = await client.prompt(session_id, "do the thing")
    assert stop == "end_turn"
    # the streamed update was captured
    assert any(u.get("update", {}).get("sessionUpdate") == "agent_message_chunk" for u in client.updates)
    await client.close()


@pytest.mark.asyncio
async def test_acp_runner_drives_agent_to_completion() -> None:
    runner = AcpRunner(agent_command=[sys.executable, _MOCK_AGENT])
    handle = await runner.spawn(
        task_id="t1",
        swarm_id="s1",
        mcp_endpoint="http://localhost:8800/sse",
        prompt="work",
        cwd=".",
    )
    assert handle.runtime == "acp"
    drive_task = handle.extra["_drive_task"]
    await drive_task  # should complete cleanly (auto-approves permission)
    status = await runner.status(handle)
    assert status.running is False
