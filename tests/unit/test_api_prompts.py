from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.prompts import build_prompts_routes
from minder.store.interfaces import IOperationalStore


def _prompt(**overrides: object) -> SimpleNamespace:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "debug_custom",
        "title": "Debug Custom",
        "description": "Custom debug prompt",
        "content_template": "Investigate {error}",
        "arguments": ["error"],
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _build_client(store: AsyncMock, sync_hook: AsyncMock | None = None) -> TestClient:
    context = AdminRouteContext.build(
        config=Settings(),
        store=store,
        cache=None,
        prompt_sync_hook=sync_hook,
    )
    app = Starlette(routes=build_prompts_routes(context))
    app.state.config = Settings()
    return TestClient(app)


def test_list_prompts_returns_serialized_rows() -> None:
    store = AsyncMock(spec=IOperationalStore)
    store.list_prompts.return_value = [_prompt(name="review_plus")]
    client = _build_client(store)

    response = client.get("/api/v1/prompts")

    assert response.status_code == 200
    data = response.json()
    assert [prompt["name"] for prompt in data[:5]] == [
        "debug",
        "explain",
        "query_reasoning",
        "review",
        "tdd_step",
    ]
    assert data[0]["is_builtin"] is True
    assert data[-1]["name"] == "review_plus"
    assert data[-1]["arguments"] == ["error"]


def test_create_prompt_triggers_runtime_sync() -> None:
    store = AsyncMock(spec=IOperationalStore)
    sync_hook = AsyncMock()
    created = _prompt(name="triage", title="Triage Prompt")
    store.create_prompt.return_value = created
    client = _build_client(store, sync_hook)

    response = client.post(
        "/api/v1/prompts",
        json={
            "name": "triage",
            "title": "Triage Prompt",
            "description": "Summarize incident context",
            "content_template": "Analyze {incident}",
            "arguments": ["incident"],
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "triage"
    sync_hook.assert_awaited_once()


def test_update_prompt_returns_full_resource() -> None:
    store = AsyncMock(spec=IOperationalStore)
    sync_hook = AsyncMock()
    prompt_id = uuid.uuid4()
    store.update_prompt.return_value = _prompt(id=prompt_id, name="triage_v2")
    client = _build_client(store, sync_hook)

    response = client.patch(
        f"/api/v1/prompts/{prompt_id}",
        json={"name": "triage_v2"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "triage_v2"
    sync_hook.assert_awaited_once()


def test_delete_prompt_returns_json_payload() -> None:
    store = AsyncMock(spec=IOperationalStore)
    sync_hook = AsyncMock()
    prompt_id = uuid.uuid4()
    client = _build_client(store, sync_hook)

    response = client.delete(f"/api/v1/prompts/{prompt_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    sync_hook.assert_awaited_once()


def test_polish_prompt_returns_llm_metadata(monkeypatch) -> None:
    store = AsyncMock(spec=IOperationalStore)
    client = _build_client(store)

    def fake_polish_prompt_draft(draft, config):
        del config
        return draft, {
            "provider": "litert_lm",
            "model": "gemma-4-e4b-it",
            "runtime": "llama_cpp",
        }

    monkeypatch.setattr(
        "minder.presentation.http.admin.prompts.polish_prompt_draft",
        fake_polish_prompt_draft,
    )

    response = client.post(
        "/api/v1/prompts/polish",
        json={
            "name": "explain_plus",
            "title": "Explain Plus",
            "description": "",
            "content_template": "Explain {code}",
            "arguments": ["code"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["model"] == "gemma-4-e4b-it"
    assert payload["name"] == "explain_plus"
