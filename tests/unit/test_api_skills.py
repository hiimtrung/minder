from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.skills import build_skills_routes
from minder.store.interfaces import IOperationalStore


def _skill(**overrides: object) -> SimpleNamespace:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid.uuid4(),
        "title": "Testing workflow skill",
        "content": "Write failing tests before implementation.",
        "language": "markdown",
        "tags": ["tdd", "test_plan", "source:phase_4_4"],
        "usage_count": 3,
        "quality_score": 0.9,
        "source_metadata": None,
        "excerpt_kind": "none",
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _build_client(store: AsyncMock) -> TestClient:
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_skills_routes(context))
    app.state.config = Settings()
    return TestClient(app)


def test_list_skills_returns_serialized_rows() -> None:
    store = AsyncMock(spec=IOperationalStore)
    store.list_skills.return_value = [_skill()]
    client = _build_client(store)

    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "Testing workflow skill"
    assert payload[0]["provenance"] == "phase_4_4"
    assert payload[0]["artifact_type_tags"] == ["test_plan"]


def test_create_skill_returns_created_payload() -> None:
    store = AsyncMock(spec=IOperationalStore)
    created = _skill(id=uuid.uuid4(), title="Created skill")
    store.create_skill.return_value = created
    client = _build_client(store)

    response = client.post(
        "/api/v1/skills",
        json={
            "title": "Created skill",
            "content": "Summarize the failing test before implementation.",
            "language": "markdown",
            "tags": ["triage"],
            "workflow_steps": ["Test Writing"],
            "artifact_types": ["test_plan"],
            "provenance": "dashboard",
            "quality_score": 0.7,
        },
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Created skill"


def test_update_skill_returns_full_resource() -> None:
    store = AsyncMock(spec=IOperationalStore)
    skill_id = uuid.uuid4()
    store.get_skill_by_id.return_value = _skill(id=skill_id)
    store.update_skill.return_value = _skill(id=skill_id, title="Updated skill")
    client = _build_client(store)

    response = client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"title": "Updated skill", "quality_score": 1.0},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated skill"


def test_delete_skill_returns_json_payload() -> None:
    store = AsyncMock(spec=IOperationalStore)
    skill_id = uuid.uuid4()
    store.get_skill_by_id.return_value = _skill(id=skill_id)
    client = _build_client(store)

    response = client.delete(f"/api/v1/skills/{skill_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}


def test_import_skills_returns_summary() -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)

    with patch(
        "minder.presentation.http.admin.skills.SkillTools.minder_skill_import_git",
        new=AsyncMock(
            return_value={
                "provider": "generic_git",
                "repo_url": "https://example.com/skills.git",
                "path": "skills",
                "created_count": 1,
                "updated_count": 0,
                "imported_count": 1,
                "imported": [
                    {
                        "action": "created",
                        "id": str(uuid.uuid4()),
                        "title": "Imported skill",
                        "source": {"path": "skills"},
                    }
                ],
            }
        ),
    ):
        response = client.post(
            "/api/v1/skills/imports",
            json={
                "repo_url": "https://example.com/skills.git",
                "path": "skills",
                "provider": "generic_git",
            },
        )

    assert response.status_code == 201
    assert response.json()["imported_count"] == 1
