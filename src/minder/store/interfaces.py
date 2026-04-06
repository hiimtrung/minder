"""
Domain Repository Interfaces — Clean Architecture boundary.

These Protocol classes define the contracts that all store adapters
(SQLite, MongoDB, etc.) must satisfy. The application layer depends
only on these interfaces, never on concrete implementations.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# User Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IUserRepository(Protocol):
    async def create_user(self, **kwargs: Any) -> Any: ...
    async def get_user_by_id(self, user_id: uuid.UUID) -> Any | None: ...
    async def get_user_by_email(self, email: str) -> Any | None: ...
    async def get_user_by_username(self, username: str) -> Any | None: ...
    async def list_users(self, active_only: bool = True) -> list[Any]: ...
    async def update_user(self, user_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_user(self, user_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Skill Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class ISkillRepository(Protocol):
    async def create_skill(self, **kwargs: Any) -> Any: ...
    async def get_skill_by_id(self, skill_id: uuid.UUID) -> Any | None: ...
    async def list_skills(self) -> list[Any]: ...
    async def delete_skill(self, skill_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Session Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class ISessionRepository(Protocol):
    async def create_session(self, **kwargs: Any) -> Any: ...
    async def get_session_by_id(self, session_id: uuid.UUID) -> Any | None: ...
    async def get_sessions_by_user(self, user_id: uuid.UUID) -> list[Any]: ...
    async def update_session(self, session_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_session(self, session_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Workflow Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IWorkflowRepository(Protocol):
    async def create_workflow(self, **kwargs: Any) -> Any: ...
    async def get_workflow_by_id(self, workflow_id: uuid.UUID) -> Any | None: ...
    async def get_workflow_by_name(self, name: str) -> Any | None: ...
    async def list_workflows(self) -> list[Any]: ...
    async def update_workflow(self, workflow_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_workflow(self, workflow_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Repository (code repository) Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IRepositoryRepo(Protocol):
    async def create_repository(self, **kwargs: Any) -> Any: ...
    async def get_repository_by_id(self, repo_id: uuid.UUID) -> Any | None: ...
    async def get_repository_by_name(self, repo_name: str) -> Any | None: ...
    async def list_repositories(self) -> list[Any]: ...
    async def update_repository(self, repo_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_repository(self, repo_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Workflow State Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IWorkflowStateRepository(Protocol):
    async def create_workflow_state(self, **kwargs: Any) -> Any: ...
    async def get_workflow_state_by_id(self, state_id: uuid.UUID) -> Any | None: ...
    async def get_workflow_state_by_repo(self, repo_id: uuid.UUID) -> Any | None: ...
    async def update_workflow_state(self, state_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_workflow_state(self, state_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Document Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IDocumentRepository(Protocol):
    async def create_document(
        self,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        *,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Any: ...

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> Any | None: ...

    async def list_documents(self, project: str | None = None) -> list[Any]: ...

    async def upsert_document(
        self,
        *,
        title: str,
        content: str,
        doc_type: str,
        source_path: str,
        project: str,
        chunks: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> Any: ...

    async def delete_documents_not_in_paths(
        self, *, project: str, keep_paths: set[str]
    ) -> None: ...


# ---------------------------------------------------------------------------
# History Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IHistoryRepository(Protocol):
    async def create_history(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        reasoning_trace: str | None = None,
        tool_calls: dict[str, Any] | None = None,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> Any: ...

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[Any]: ...
    async def list_history_for_user(self, user_id: uuid.UUID) -> list[Any]: ...


# ---------------------------------------------------------------------------
# Error Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IErrorRepository(Protocol):
    async def create_error(
        self,
        error_code: str,
        error_message: str,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
        resolution: str | None = None,
        embedding: list[float] | None = None,
        resolved: bool = False,
    ) -> Any: ...

    async def list_errors(self) -> list[Any]: ...
    async def search_errors(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Cache Provider (for Redis)
# ---------------------------------------------------------------------------


@runtime_checkable
class ICacheProvider(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def expire(self, key: str, ttl: int) -> None: ...
    async def incr(self, key: str) -> int: ...
    async def keys(self, pattern: str) -> list[str]: ...
    async def flush_namespace(self, namespace: str) -> None: ...
    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Vector Store
# ---------------------------------------------------------------------------


@runtime_checkable
class IVectorStore(Protocol):
    async def upsert_document(
        self,
        doc_id: uuid.UUID,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> None: ...

    async def delete_documents(self, doc_ids: list[uuid.UUID]) -> None: ...

    async def search_documents(
        self,
        query_embedding: list[float],
        *,
        project: str | None = None,
        doc_types: set[str] | None = None,
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]: ...

    async def setup(self) -> None: ...


# ---------------------------------------------------------------------------
# Operational Store — composite interface for backwards compatibility
# ---------------------------------------------------------------------------


@runtime_checkable
class IOperationalStore(
    IUserRepository,
    ISkillRepository,
    ISessionRepository,
    IWorkflowRepository,
    IRepositoryRepo,
    IWorkflowStateRepository,
    IDocumentRepository,
    IHistoryRepository,
    IErrorRepository,
    Protocol,
):
    """
    Composite interface matching the current RelationalStore surface.

    This allows existing code that depends on a single store object
    (e.g., server.py, tools) to continue working while we migrate
    individual repositories to MongoDB behind the scenes.
    """

    async def init_db(self) -> None: ...
    async def dispose(self) -> None: ...
