from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.application.admin.jobs import AdminJobService
from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.jobs import build_jobs_routes
from minder.store.interfaces import IOperationalStore


def _job(**overrides: object) -> SimpleNamespace:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid.uuid4(),
        "job_type": "skill_import_git",
        "title": "Import skills from https://example.com/repo.git",
        "status": "queued",
        "requested_by_user_id": uuid.uuid4(),
        "payload": {
            "repo_url": "https://example.com/repo.git",
            "path": "skills",
        },
        "result_payload": None,
        "error_message": None,
        "progress_current": 0,
        "progress_total": 0,
        "message": "Queued",
        "events": [],
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _build_client(
    store: AsyncMock, job_service: AdminJobService | None = None
) -> TestClient:
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_jobs_routes(context))
    app.state.config = Settings()
    if job_service is not None:
        app.state.job_service = job_service
    return TestClient(app)


def test_create_job_returns_accepted_payload() -> None:
    store = AsyncMock(spec=IOperationalStore)
    service = AdminJobService(store, Settings())
    queued_job = _job()
    service.enqueue = AsyncMock(return_value=queued_job)  # type: ignore[method-assign]
    client = _build_client(store, service)

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    ):
        response = client.post(
            "/api/v1/jobs",
            json={
                "job_type": "skill_import_git",
                "payload": {
                    "repo_url": "https://example.com/repo.git",
                    "path": "skills",
                    "provider": "generic_git",
                },
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_type"] == "skill_import_git"
    assert payload["status"] == "queued"
    assert payload["payload"]["repo_url"] == "https://example.com/repo.git"


def test_list_jobs_returns_serialized_rows() -> None:
    store = AsyncMock(spec=IOperationalStore)
    store.list_admin_jobs.return_value = [
        _job(status="completed", progress_current=3, progress_total=3)
    ]
    client = _build_client(store)

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    ):
        response = client.get(
            "/api/v1/jobs?job_type=skill_import_git&status=completed&limit=5"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 5
    assert payload["jobs"][0]["status"] == "completed"
    assert payload["jobs"][0]["progress_percent"] == 100.0
    store.list_admin_jobs.assert_awaited_once_with(
        job_type="skill_import_git",
        status="completed",
        limit=5,
    )


def test_get_job_returns_serialized_snapshot() -> None:
    store = AsyncMock(spec=IOperationalStore)
    existing_job = _job(status="running", progress_current=1, progress_total=4)
    store.get_admin_job_by_id.return_value = existing_job
    client = _build_client(store)

    with patch.object(
        AdminRouteContext,
        "admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    ):
        response = client.get(f"/api/v1/jobs/{existing_job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(existing_job.id)
    assert payload["status"] == "running"
    assert payload["progress_percent"] == 25.0


@pytest.mark.asyncio
async def test_admin_job_service_runs_skill_import_and_records_completion() -> None:
    store = AsyncMock(spec=IOperationalStore)
    job_id = uuid.uuid4()
    base_job = _job(id=job_id, status="running", message="Starting job")
    progress_job = _job(
        id=job_id,
        status="running",
        message="Scanning repository",
        progress_current=1,
        progress_total=3,
        events=[],
    )
    completed_job = _job(
        id=job_id,
        status="running",
        message="Scanning repository",
        progress_current=1,
        progress_total=3,
        events=[],
    )

    store.get_admin_job_by_id.side_effect = [
        base_job,
        progress_job,
        completed_job,
    ]
    store.update_admin_job.return_value = completed_job
    service = AdminJobService(store, Settings())

    async def _fake_import(**kwargs: object) -> dict[str, object]:
        progress_callback = kwargs["progress_callback"]
        await progress_callback(
            {
                "event_type": "scan",
                "message": "Scanning repository",
                "progress_current": 1,
                "progress_total": 3,
            }
        )
        return {
            "provider": "generic_git",
            "repo_url": "https://example.com/repo.git",
            "path": "skills",
            "created_count": 2,
            "updated_count": 1,
            "imported_count": 3,
            "imported": [],
        }

    with patch(
        "minder.application.admin.jobs.SkillTools.minder_skill_import_git",
        new=AsyncMock(side_effect=_fake_import),
    ):
        await service._run_skill_import(str(job_id))

    assert store.update_admin_job.await_count == 2
    progress_call = store.update_admin_job.await_args_list[0]
    completed_call = store.update_admin_job.await_args_list[1]

    assert progress_call.args[0] == job_id
    assert progress_call.kwargs["status"] == "running"
    assert progress_call.kwargs["progress_current"] == 1
    assert progress_call.kwargs["progress_total"] == 3

    assert completed_call.args[0] == job_id
    assert completed_call.kwargs["status"] == "completed"
    assert completed_call.kwargs["progress_current"] == 3
    assert completed_call.kwargs["progress_total"] == 3
    assert completed_call.kwargs["result_payload"]["imported_count"] == 3
