from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

from starlette.applications import Starlette
from starlette.testclient import TestClient

from minder.config import Settings
from minder.presentation.http.admin.context import AdminRouteContext
from minder.presentation.http.admin.runtime import build_runtime_routes
from minder.store.interfaces import IOperationalStore


def test_runtime_query_returns_query_result() -> None:
    store = AsyncMock(spec=IOperationalStore)
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_runtime_routes(context))
    app.state.config = Settings()
    client = TestClient(app)
    repo_id = uuid.uuid4()

    with patch(
        "minder.presentation.http.admin.runtime.AdminRouteContext.admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), role="admin")),
    ), patch.object(
        context.use_cases,
        "get_repository_detail",
        new=AsyncMock(
            return_value={
                "repository": {
                    "id": str(repo_id),
                    "name": "minder",
                    "path": "/tmp/minder",
                }
            }
        ),
    ), patch(
        "minder.presentation.http.admin.runtime.QueryTools.minder_query",
        new=AsyncMock(
            return_value={
                "answer": "Instruction envelope:\n{}\n\nUser query:\nWhat should I inspect first?\n\nRetrieved context:\nNone",
                "sources": [{"path": "src/minder/presentation/http/admin/runtime.py"}],
                "workflow": {},
                "guard_result": None,
                "verification_result": None,
                "evaluation": None,
                "provider": "local",
                "model": "gemma",
                "runtime": "auto",
                "orchestration_runtime": "langgraph",
                "transition_log": [{"edge": "complete"}],
                "edge": "complete",
                "cross_repo_graph": None,
            }
        ),
    ):
        response = client.post(
            "/api/v1/runtime/query",
            json={
                "query": "What should I inspect first?",
                "repo_id": str(repo_id),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_sanitized"] is True
    assert "Start by inspecting" in payload["answer"]
    assert payload["answer_warning"] is not None
    assert payload["repository"]["path"] == "/tmp/minder"


def test_runtime_query_stream_returns_chunked_events() -> None:
    store = AsyncMock(spec=IOperationalStore)
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_runtime_routes(context))
    app.state.config = Settings()
    client = TestClient(app)
    repo_id = uuid.uuid4()

    async def fake_stream(*args, **kwargs):  # noqa: ANN002, ANN003
        yield {"type": "attempt", "attempt": 1}
        yield {"type": "chunk", "attempt": 1, "delta": "Hello"}
        yield {
            "type": "final",
            "payload": {
                "answer": "Hello world",
                "sources": [{"path": "src/minder/presentation/http/admin/runtime.py"}],
                "workflow": {},
                "guard_result": None,
                "verification_result": None,
                "evaluation": None,
                "provider": "local",
                "model": "gemma",
                "runtime": "auto",
                "orchestration_runtime": "internal",
                "transition_log": [{"edge": "complete"}],
                "edge": "complete",
                "cross_repo_graph": None,
            },
        }

    with patch(
        "minder.presentation.http.admin.runtime.AdminRouteContext.admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), role="admin")),
    ), patch.object(
        context.use_cases,
        "get_repository_detail",
        new=AsyncMock(
            return_value={
                "repository": {
                    "id": str(repo_id),
                    "name": "minder",
                    "path": "/tmp/minder",
                }
            }
        ),
    ), patch(
        "minder.presentation.http.admin.runtime.QueryTools.minder_query_stream",
        new=fake_stream,
    ):
        response = client.post(
            "/api/v1/runtime/query/stream",
            json={
                "query": "Stream this answer",
                "repo_id": str(repo_id),
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert any('"type": "attempt"' in line for line in lines)
    assert any('"type": "chunk"' in line for line in lines)
    assert any('"type": "final"' in line for line in lines)


def test_runtime_query_allows_missing_repository_scope() -> None:
    store = AsyncMock(spec=IOperationalStore)
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_runtime_routes(context))
    app.state.config = Settings()
    client = TestClient(app)

    with patch(
        "minder.presentation.http.admin.runtime.AdminRouteContext.admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), role="admin")),
    ), patch(
        "minder.presentation.http.admin.runtime.QueryTools.minder_query",
        new=AsyncMock(
            return_value={
                "answer": "General dashboard guidance.",
                "sources": [],
                "workflow": {},
                "guard_result": None,
                "verification_result": None,
                "evaluation": None,
                "provider": "local",
                "model": "gemma",
                "runtime": "auto",
                "orchestration_runtime": "internal",
                "transition_log": [{"edge": "complete"}],
                "edge": "complete",
                "cross_repo_graph": None,
            }
        ),
    ) as query_mock:
        response = client.post(
            "/api/v1/runtime/query",
            json={
                "query": "What can this dashboard do?",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository"] == {"id": None, "name": None, "path": None}
    query_mock.assert_awaited_once()
    assert query_mock.await_args.kwargs["repo_path"] is None
    assert query_mock.await_args.kwargs["repo_id"] is None


def test_runtime_query_executes_safe_memory_action_before_query_fallback() -> None:
    store = AsyncMock(spec=IOperationalStore)
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_runtime_routes(context))
    app.state.config = Settings()
    client = TestClient(app)
    admin_id = uuid.uuid4()

    with patch(
        "minder.presentation.http.admin.runtime.AdminRouteContext.admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=admin_id, role="admin")),
    ), patch(
        "minder.presentation.http.admin.runtime.MemoryTools.minder_memory_store",
        new=AsyncMock(return_value={"id": "memory-1", "title": "Release note"}),
    ) as memory_store_mock, patch(
        "minder.presentation.http.admin.runtime.QueryTools.minder_query",
        new=AsyncMock(),
    ) as query_mock:
        response = client.post(
            "/api/v1/runtime/query",
            json={
                "query": 'create memory title "Release note" content "Ship phase 6 safely" tags "release,phase6"',
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["edge"] == "agent_tool_executed"
    assert payload["agent_actions"][0]["tool"] == "minder_memory_store"
    assert payload["answer"] == "Created memory 'Release note' with id memory-1."
    query_mock.assert_not_awaited()
    memory_store_mock.assert_awaited_once()


def test_runtime_query_stream_executes_safe_session_action() -> None:
    store = AsyncMock(spec=IOperationalStore)
    context = AdminRouteContext.build(config=Settings(), store=store, cache=None)
    app = Starlette(routes=build_runtime_routes(context))
    app.state.config = Settings()
    client = TestClient(app)
    admin_id = uuid.uuid4()

    with patch(
        "minder.presentation.http.admin.runtime.AdminRouteContext.admin_user_from_request",
        new=AsyncMock(return_value=SimpleNamespace(id=admin_id, role="admin")),
    ), patch(
        "minder.presentation.http.admin.runtime.SessionTools.minder_session_cleanup",
        new=AsyncMock(return_value={"deleted_sessions": 2, "deleted_history": 4}),
    ) as cleanup_mock, patch(
        "minder.presentation.http.admin.runtime.QueryTools.minder_query_stream",
        new=AsyncMock(),
    ) as query_stream_mock:
        response = client.post(
            "/api/v1/runtime/query/stream",
            json={
                "query": "cleanup expired sessions",
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert any('"type": "final"' in line for line in lines)
    assert any("minder_session_cleanup" in line for line in lines)
    cleanup_mock.assert_awaited_once_with(user_id=admin_id)
    query_stream_mock.assert_not_called()
