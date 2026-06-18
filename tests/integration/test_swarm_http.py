from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.application.swarm.service import SwarmService
from minder.config import MinderConfig
from minder.presentation.http.admin.swarm import build_swarm_routes
from minder.store.swarm import SwarmStore


@pytest.fixture
async def seeded(tmp_path):
    store = SwarmStore(db_path=str(tmp_path / "swarm.db"))
    await store.init_db()
    config = MinderConfig()
    service = SwarmService(store, config)
    sw = await service.create_swarm(goal="ship feature")
    swarm_id = sw["swarm_id"]
    await service.plan(swarm_id=swarm_id, tasks=[{"title": "design", "runtime_hint": "claude"}])
    await service.propose(swarm_id=swarm_id)
    yield store, config, swarm_id
    await store.dispose()


def _client(store, config) -> TestClient:
    context = SimpleNamespace(swarm_store=store, config=config)
    app = Starlette(routes=build_swarm_routes(context))
    return TestClient(app)


@pytest.mark.asyncio
async def test_http_list_get_and_approve(seeded) -> None:
    store, config, swarm_id = seeded
    client = _client(store, config)

    # list
    r = client.get("/api/v1/swarms")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert any(s["swarm_id"] == swarm_id for s in body["swarms"])

    # detail shows manifest pending approval + the task
    r = client.get(f"/api/v1/swarms/{swarm_id}")
    assert r.status_code == 200
    d = r.json()
    assert d["manifest"]["status"] == "pending_approval"
    assert len(d["tasks"]) == 1

    # approve via HTTP (the human gate)
    r = client.post(f"/api/v1/swarms/{swarm_id}/approve", json={"action": "approve"})
    assert r.status_code == 200
    assert r.json()["manifest_status"] == "approved"

    # now reflects approved
    d = client.get(f"/api/v1/swarms/{swarm_id}").json()
    assert d["manifest"]["status"] == "approved"
