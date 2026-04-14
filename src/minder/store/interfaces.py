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
    async def has_admin_users(self) -> bool: ...


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
    async def get_sessions_by_client(self, client_id: uuid.UUID) -> list[Any]: ...
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

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[Any]: ...

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
# Rule Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IRuleRepository(Protocol):
    async def create_rule(self, **kwargs: Any) -> Any: ...
    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Any | None: ...
    async def list_rules(self) -> list[Any]: ...
    async def list_by_scope(self, scope: str) -> list[Any]: ...
    async def list_active(self) -> list[Any]: ...
    async def update_rule(self, rule_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_rule(self, rule_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Feedback Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IFeedbackRepository(Protocol):
    async def create_feedback(self, **kwargs: Any) -> Any: ...
    async def get_feedback_by_id(self, feedback_id: uuid.UUID) -> Any | None: ...
    async def list_feedback(self) -> list[Any]: ...
    async def list_by_entity(self, entity_type: str, entity_id: uuid.UUID) -> list[Any]: ...
    async def average_rating(self, entity_id: uuid.UUID) -> float | None: ...
    async def update_feedback(self, feedback_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def delete_feedback(self, feedback_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Knowledge Graph Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IGraphRepository(Protocol):
    async def add_node(
        self, node_type: str, name: str, metadata: dict[str, Any] | None = None, node_id: uuid.UUID | None = None
    ) -> Any: ...
    async def upsert_node(
        self, node_type: str, name: str, metadata: dict[str, Any] | None = None
    ) -> Any: ...
    async def get_node(self, node_id: uuid.UUID) -> Any | None: ...
    async def get_node_by_name(self, node_type: str, name: str) -> Any | None: ...
    async def query_by_type(self, node_type: str) -> list[Any]: ...
    async def delete_node(self, node_id: uuid.UUID) -> None: ...
    async def add_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        edge_id: uuid.UUID | None = None,
    ) -> Any: ...
    async def upsert_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
    ) -> Any: ...
    async def delete_edge(self, edge_id: uuid.UUID) -> None: ...
    async def get_neighbors(
        self,
        node_id: uuid.UUID,
        *,
        direction: str = "out",
        relation: str | None = None,
    ) -> list[Any]: ...
    async def get_path(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        max_depth: int = 6,
    ) -> list[Any]: ...


# ---------------------------------------------------------------------------
# Client Gateway Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IClientRepository(Protocol):
    async def create_client(self, **kwargs: Any) -> Any: ...
    async def get_client_by_id(self, client_id: uuid.UUID) -> Any | None: ...
    async def get_client_by_slug(self, slug: str) -> Any | None: ...
    async def list_clients(self) -> list[Any]: ...
    async def update_client(self, client_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def create_client_api_key(self, **kwargs: Any) -> Any: ...
    async def list_client_api_keys(self, client_id: uuid.UUID) -> list[Any]: ...
    async def update_client_api_key(self, key_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def create_client_session(self, **kwargs: Any) -> Any: ...
    async def count_active_client_sessions(self) -> int: ...
    async def get_client_session_by_token_id(self, token_id: str) -> Any | None: ...
    async def update_client_session(self, session_id: uuid.UUID, **kwargs: Any) -> Any | None: ...
    async def create_audit_log(self, **kwargs: Any) -> Any: ...
    async def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Any]: ...
    async def count_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
    ) -> int: ...
    async def get_audit_summary(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        group_by: str = "event_type",
    ) -> dict[str, int]: ...


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
    IRuleRepository,
    IFeedbackRepository,
    IClientRepository,
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
