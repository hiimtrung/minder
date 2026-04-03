from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from minder.auth.service import AuthService
from minder.config import MinderConfig, Settings
from minder.store.relational import RelationalStore
from minder.store.repo_state import RepoStateStore
from minder.tools.auth import AuthTools
from minder.tools.query import QueryTools
from minder.tools.search import SearchTools
from minder.tools.session import SessionTools
from minder.tools.workflow import WorkflowTools
from minder.tools.memory import MemoryTools
from minder.transport import SSETransport, StdioTransport


def build_store(config: MinderConfig) -> RelationalStore:
    db_path = config.relational_store.db_path
    if db_path.startswith(("sqlite+", "postgresql+", "postgres://")):
        db_url = db_path
    else:
        expanded = Path(db_path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite+aiosqlite:///{expanded}"
    return RelationalStore(db_url)


def build_transport(
    *,
    config: MinderConfig,
    store: RelationalStore,
) -> SSETransport | StdioTransport:
    auth_service = AuthService(store, config)
    repo_state_store = RepoStateStore(config.workflow.repo_state_dir)
    auth_tools = AuthTools(store, auth_service)
    session_tools = SessionTools(store)
    workflow_tools = WorkflowTools(store, repo_state_store)
    memory_tools = MemoryTools(store, config)
    search_tools = SearchTools(store, config)
    query_tools = QueryTools(store, config)

    transport: SSETransport | StdioTransport
    if config.server.transport == "stdio":
        transport = StdioTransport(config=config, auth_service=auth_service)
    else:
        transport = SSETransport(config=config, auth_service=auth_service)

    async def minder_auth_login(api_key: str) -> dict[str, str]:
        return await auth_tools.minder_auth_login(api_key)

    async def minder_auth_whoami(*, user) -> dict[str, str]:  # noqa: ANN001
        token = auth_service.issue_jwt(user)
        return await auth_tools.minder_auth_whoami(token)

    async def minder_auth_manage(*, user, action: str) -> dict[str, object]:  # noqa: ANN001
        return await auth_tools.minder_auth_manage(actor_user_id=user.id, action=action)

    async def minder_session_create(
        *, user, repo_id: str | None = None, project_context: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        return await session_tools.minder_session_create(
            user_id=user.id,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            project_context=project_context,
        )

    async def minder_session_save(
        *, user, session_id: str, state: dict[str, Any] | None = None, active_skills: dict[str, Any] | None = None  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_save(
            uuid.UUID(session_id),
            state=state,
            active_skills=active_skills,
        )

    async def minder_session_restore(*, user, session_id: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await session_tools.minder_session_restore(uuid.UUID(session_id))

    async def minder_session_context(
        *, user, session_id: str, branch: str, open_files: list[str]  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await session_tools.minder_session_context(
            uuid.UUID(session_id),
            branch=branch,
            open_files=open_files,
        )

    async def minder_workflow_get(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_get(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_step(*, user, repo_id: str, repo_path: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_step(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
        )

    async def minder_workflow_update(
        *,
        user,
        repo_id: str,
        repo_path: str,
        completed_step: str,
        artifact_name: str | None = None,
        artifact_content: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_update(
            repo_id=uuid.UUID(repo_id),
            repo_path=repo_path,
            completed_step=completed_step,
            artifact_name=artifact_name,
            artifact_content=artifact_content,
        )

    async def minder_workflow_guard(*, user, repo_id: str, requested_step: str) -> dict[str, Any]:  # noqa: ANN001
        del user
        return await workflow_tools.minder_workflow_guard(
            repo_id=uuid.UUID(repo_id),
            requested_step=requested_step,
        )

    async def minder_memory_store(
        *, user, title: str, content: str, tags: list[str], language: str  # noqa: ANN001
    ) -> dict[str, Any]:
        del user
        return await memory_tools.minder_memory_store(
            title=title,
            content=content,
            tags=tags,
            language=language,
        )

    async def minder_memory_recall(*, user, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_recall(query, limit=limit)

    async def minder_memory_list(*, user) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_list()

    async def minder_memory_delete(*, user, skill_id: str) -> dict[str, bool]:  # noqa: ANN001
        del user
        return await memory_tools.minder_memory_delete(skill_id)

    async def minder_search(*, user, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await search_tools.minder_search(query, limit=limit)

    async def minder_query(
        *,
        user,
        query: str,
        repo_path: str,
        session_id: str | None = None,
        repo_id: str | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:  # noqa: ANN001
        return await query_tools.minder_query(
            query,
            repo_path=repo_path,
            session_id=uuid.UUID(session_id) if session_id else None,
            user_id=user.id,
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            workflow_name=workflow_name,
        )

    async def minder_search_code(*, user, query: str, repo_path: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_code(query, repo_path=repo_path, limit=limit)

    async def minder_search_errors(*, user, query: str, limit: int = 5) -> list[dict[str, Any]]:  # noqa: ANN001
        del user
        return await query_tools.minder_search_errors(query, limit=limit)

    transport.register_tool("minder_auth_login", minder_auth_login, require_auth=False)
    transport.register_tool("minder_auth_whoami", minder_auth_whoami, require_auth=True)
    transport.register_tool("minder_auth_manage", minder_auth_manage, require_auth=True)
    transport.register_tool("minder_session_create", minder_session_create, require_auth=True)
    transport.register_tool("minder_session_save", minder_session_save, require_auth=True)
    transport.register_tool("minder_session_restore", minder_session_restore, require_auth=True)
    transport.register_tool("minder_session_context", minder_session_context, require_auth=True)
    transport.register_tool("minder_workflow_get", minder_workflow_get, require_auth=True)
    transport.register_tool("minder_workflow_step", minder_workflow_step, require_auth=True)
    transport.register_tool("minder_workflow_update", minder_workflow_update, require_auth=True)
    transport.register_tool("minder_workflow_guard", minder_workflow_guard, require_auth=True)
    transport.register_tool("minder_memory_store", minder_memory_store, require_auth=True)
    transport.register_tool("minder_memory_recall", minder_memory_recall, require_auth=True)
    transport.register_tool("minder_memory_list", minder_memory_list, require_auth=True)
    transport.register_tool("minder_memory_delete", minder_memory_delete, require_auth=True)
    transport.register_tool("minder_search", minder_search, require_auth=True)
    transport.register_tool("minder_query", minder_query, require_auth=True)
    transport.register_tool("minder_search_code", minder_search_code, require_auth=True)
    transport.register_tool("minder_search_errors", minder_search_errors, require_auth=True)
    return transport


async def _run() -> None:
    config = Settings()
    store = build_store(config)
    await store.init_db()
    transport = build_transport(config=config, store=store)
    try:
        if transport.transport_name == "stdio":
            transport.app.run(transport="stdio")
        else:
            transport.app.run(transport="sse")
    finally:
        await store.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
