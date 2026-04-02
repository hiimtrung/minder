from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from minder.config import MinderConfig  # noqa: E402
from minder.graph import MinderGraph  # noqa: E402
from minder.store.error import ErrorStore  # noqa: E402
from minder.store.history import HistoryStore  # noqa: E402
from minder.store.relational import RelationalStore  # noqa: E402
from minder.tools.query import QueryTools  # noqa: E402

IN_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "repo"
        repo_path.mkdir()
        (repo_path / "feature.py").write_text(
            "def work(value: int) -> int:\n    return value + 1\n",
            encoding="utf-8",
        )
        (repo_path / "README.md").write_text(
            "# Demo Repo\n\nThis repository is used for Phase 2 manual smoke tests.\n",
            encoding="utf-8",
        )

        config = MinderConfig()
        store = RelationalStore(IN_MEMORY_URL)
        await store.init_db()

        try:
            user_id, repo_id, session_id = await seed(store, repo_path)
            graph = MinderGraph(
                store,
                config,
                history_store=HistoryStore(store),
                error_store=ErrorStore(store),
            )
            tools = QueryTools(store, config, graph=graph)

            query_result = await tools.minder_query(
                "write tests for work and explain the implementation path",
                repo_path=str(repo_path),
                user_id=user_id,
                repo_id=repo_id,
                session_id=session_id,
                workflow_name="tdd",
                verification_payload={"language": "python", "code": "print('ok')"},
            )
            code_hits = await tools.minder_search_code("work implementation", repo_path=str(repo_path))
            error_hits = await tools.minder_search_errors("verification failed")
            workflow_state = await store.get_workflow_state_by_repo(repo_id)

            output = {
                "provider": query_result["provider"],
                "runtime": query_result["runtime"],
                "edge": query_result["edge"],
                "orchestration_runtime": query_result["orchestration_runtime"],
                "verification_result": query_result["verification_result"],
                "workflow_current_step": workflow_state.current_step if workflow_state else None,
                "workflow_completed_steps": workflow_state.completed_steps if workflow_state else [],
                "code_search_hits": code_hits[:3],
                "error_search_hits": error_hits[:3],
                "query_sources": query_result["sources"],
            }
            print(json.dumps(output, indent=2, default=str))
        finally:
            await store.dispose()


async def seed(
    store: RelationalStore, repo_path: Path
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await store.create_user(
        id=uuid.uuid4(),
        email="manual@example.com",
        username="manual",
        display_name="Manual Test",
        api_key_hash="hash",
        role="member",
        is_active=True,
        settings={},
    )
    workflow = await store.create_workflow(
        id=uuid.uuid4(),
        name="tdd",
        version=1,
        steps=[{"name": "Test Writing"}, {"name": "Implementation"}],
        policies={"block_step_skips": True},
        default_for_repo=True,
    )
    repo = await store.create_repository(
        id=uuid.uuid4(),
        repo_name=repo_path.name,
        repo_url="https://example.com/manual",
        default_branch="main",
        workflow_id=workflow.id,
        state_path=str(repo_path / ".minder"),
        context_snapshot={},
        relationships={},
    )
    session = await store.create_session(
        id=uuid.uuid4(),
        user_id=user.id,
        repo_id=repo.id,
        project_context={},
        active_skills={},
        state={},
        ttl=3600,
    )
    await store.create_workflow_state(
        id=uuid.uuid4(),
        repo_id=repo.id,
        session_id=session.id,
        current_step="Test Writing",
        completed_steps=[],
        blocked_by=[],
        artifacts={},
    )
    return user.id, repo.id, session.id


if __name__ == "__main__":
    asyncio.run(main())
