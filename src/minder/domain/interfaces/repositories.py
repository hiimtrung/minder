"""
Domain Repository & Store Interfaces — Clean Architecture boundary.

These Protocol classes define the contracts that all store adapters
(SQLite, PostgreSQL, etc.) must satisfy. The application layer
depends only on these interfaces, never on concrete implementations.

Migrated from ``minder.store.interfaces`` to the domain layer so that
the Dependency Rule is respected: domain knows nothing about infrastructure.
"""

from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any, Protocol, runtime_checkable

from minder.domain.entities import (
    UserSchema,
    PromptSchema,
    SkillSchema,
    SessionSchema,
    WorkflowSchema,
    RepositorySchema,
    RepositoryWorkflowStateSchema,
    DocumentSchema,
    HistorySchema,
    ErrorSchema,
    RuleSchema,
    FeedbackSchema,
    GraphNodeSchema,
    GraphEdgeSchema,
    ClientSchema,
    ClientApiKeySchema,
    ClientSessionSchema,
    AuditLogSchema,
    AdminJobSchema,
    SubAgentSchema,
)


# ---------------------------------------------------------------------------
# User Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IUserRepository(Protocol):
    async def create_user(self, **kwargs: Any) -> UserSchema: ...
    async def get_user_by_id(self, user_id: uuid.UUID) -> UserSchema | None: ...
    async def get_user_by_email(self, email: str) -> UserSchema | None: ...
    async def get_user_by_username(self, username: str) -> UserSchema | None: ...
    async def list_users(self, active_only: bool = True) -> list[UserSchema]: ...
    async def update_user(self, user_id: uuid.UUID, **kwargs: Any) -> UserSchema | None: ...
    async def delete_user(self, user_id: uuid.UUID) -> None: ...
    async def has_admin_users(self) -> bool: ...


# ---------------------------------------------------------------------------
# Prompt Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IPromptRepository(Protocol):
    async def create_prompt(self, **kwargs: Any) -> PromptSchema: ...
    async def get_prompt_by_id(self, prompt_id: uuid.UUID) -> PromptSchema | None: ...
    async def get_prompt_by_name(self, name: str) -> PromptSchema | None: ...
    async def list_prompts(self) -> list[PromptSchema]: ...
    async def update_prompt(
        self, prompt_id: uuid.UUID, **kwargs: Any
    ) -> PromptSchema | None: ...
    async def delete_prompt(self, prompt_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Skill Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class ISkillRepository(Protocol):
    async def create_skill(self, **kwargs: Any) -> SkillSchema: ...
    async def get_skill_by_id(self, skill_id: uuid.UUID) -> SkillSchema | None: ...
    async def list_skills(self) -> list[SkillSchema]: ...
    async def list_skills_by_kind(
        self,
        *,
        is_memory: bool,
        exclude_deprecated: bool = True,
        owner_id: uuid.UUID | None = None,
    ) -> list[SkillSchema]: ...
    async def update_skill(self, skill_id: uuid.UUID, **kwargs: Any) -> SkillSchema | None: ...
    async def delete_skill(self, skill_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Session Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class ISessionRepository(Protocol):
    async def create_session(self, **kwargs: Any) -> SessionSchema: ...
    async def get_session_by_id(self, session_id: uuid.UUID) -> SessionSchema | None: ...
    async def get_sessions_by_user(self, user_id: uuid.UUID) -> list[SessionSchema]: ...
    async def get_sessions_by_client(self, client_id: uuid.UUID) -> list[SessionSchema]: ...
    async def find_session_by_name(
        self,
        name: str,
        *,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> SessionSchema | None: ...
    async def update_session(
        self, session_id: uuid.UUID, **kwargs: Any
    ) -> SessionSchema | None: ...
    async def list_sessions(self) -> list[SessionSchema]: ...
    async def delete_session(self, session_id: uuid.UUID) -> None: ...
    async def cleanup_expired_sessions(
        self,
        *,
        now: datetime | None = None,
        user_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
    ) -> dict[str, int]: ...


# ---------------------------------------------------------------------------
# Workflow Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IWorkflowRepository(Protocol):
    async def create_workflow(self, **kwargs: Any) -> WorkflowSchema: ...
    async def get_workflow_by_id(self, workflow_id: uuid.UUID) -> WorkflowSchema | None: ...
    async def get_workflow_by_name(self, name: str) -> WorkflowSchema | None: ...
    async def list_workflows(self) -> list[WorkflowSchema]: ...
    async def update_workflow(
        self, workflow_id: uuid.UUID, **kwargs: Any
    ) -> WorkflowSchema | None: ...
    async def delete_workflow(self, workflow_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Repository (code repository) Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IRepositoryRepo(Protocol):
    async def create_repository(self, **kwargs: Any) -> RepositorySchema: ...
    async def get_repository_by_id(self, repo_id: uuid.UUID) -> RepositorySchema | None: ...
    async def get_repository_by_name(self, repo_name: str) -> RepositorySchema | None: ...
    async def list_repositories(self) -> list[RepositorySchema]: ...
    async def update_repository(
        self, repo_id: uuid.UUID, **kwargs: Any
    ) -> RepositorySchema | None: ...
    async def delete_repository(self, repo_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Workflow State Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IWorkflowStateRepository(Protocol):
    async def create_workflow_state(self, **kwargs: Any) -> RepositoryWorkflowStateSchema: ...
    async def get_workflow_state_by_id(self, state_id: uuid.UUID) -> RepositoryWorkflowStateSchema | None: ...
    async def get_workflow_state_by_repo(self, repo_id: uuid.UUID, *, branch: str = "main") -> RepositoryWorkflowStateSchema | None: ...
    async def update_workflow_state(
        self, state_id: uuid.UUID, **kwargs: Any
    ) -> RepositoryWorkflowStateSchema | None: ...
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
    ) -> DocumentSchema: ...

    async def get_document_by_path(
        self, source_path: str, *, project: str | None = None
    ) -> DocumentSchema | None: ...

    async def get_documents_by_ids(self, doc_ids: list[uuid.UUID]) -> list[DocumentSchema]: ...

    async def list_documents(self, project: str | None = None) -> list[DocumentSchema]: ...

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
    ) -> DocumentSchema: ...

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
    ) -> HistorySchema: ...

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[HistorySchema]: ...
    async def list_history_for_user(self, user_id: uuid.UUID) -> list[HistorySchema]: ...
    async def delete_history_for_session(self, session_id: uuid.UUID) -> int: ...


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
    ) -> ErrorSchema: ...

    async def list_errors(self) -> list[ErrorSchema]: ...
    async def search_errors(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Rule Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IRuleRepository(Protocol):
    async def create_rule(self, **kwargs: Any) -> RuleSchema: ...
    async def get_rule_by_id(self, rule_id: uuid.UUID) -> RuleSchema | None: ...
    async def list_rules(self) -> list[RuleSchema]: ...
    async def list_by_scope(self, scope: str) -> list[RuleSchema]: ...
    async def list_active(self) -> list[RuleSchema]: ...
    async def update_rule(self, rule_id: uuid.UUID, **kwargs: Any) -> RuleSchema | None: ...
    async def delete_rule(self, rule_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Feedback Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IFeedbackRepository(Protocol):
    async def create_feedback(self, **kwargs: Any) -> FeedbackSchema: ...
    async def get_feedback_by_id(self, feedback_id: uuid.UUID) -> FeedbackSchema | None: ...
    async def list_feedback(self) -> list[FeedbackSchema]: ...
    async def list_by_entity(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> list[FeedbackSchema]: ...
    async def average_rating(self, entity_id: uuid.UUID) -> float | None: ...
    async def update_feedback(
        self, feedback_id: uuid.UUID, **kwargs: Any
    ) -> FeedbackSchema | None: ...
    async def delete_feedback(self, feedback_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Knowledge Graph Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IGraphRepository(Protocol):
    async def add_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        node_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> GraphNodeSchema: ...
    async def upsert_node(
        self,
        node_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> GraphNodeSchema: ...
    async def get_node(self, node_id: uuid.UUID) -> GraphNodeSchema | None: ...
    async def get_node_by_name(
        self,
        node_type: str,
        name: str,
        *,
        repo_id: str = "",
        branch: str = "",
    ) -> GraphNodeSchema | None: ...
    async def list_nodes(self) -> list[GraphNodeSchema]: ...
    async def list_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        node_types: set[str] | None = None,
    ) -> list[GraphNodeSchema]: ...
    async def list_edges(self) -> list[GraphEdgeSchema]: ...
    async def list_edges_by_scope(self, *, repo_id: str) -> list[GraphEdgeSchema]: ...
    async def query_by_type(
        self, node_type: str, *, repo_id: str = ""
    ) -> list[GraphNodeSchema]: ...
    async def delete_node(self, node_id: uuid.UUID) -> None: ...
    async def delete_nodes_by_scope(
        self,
        *,
        repo_id: str,
        branch: str | None = None,
        paths: set[str] | None = None,
    ) -> int: ...
    async def add_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        edge_id: uuid.UUID | None = None,
        *,
        repo_id: str = "",
    ) -> GraphEdgeSchema: ...
    async def upsert_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation: str,
        weight: float = 1.0,
        *,
        repo_id: str = "",
    ) -> GraphEdgeSchema: ...
    async def delete_edge(self, edge_id: uuid.UUID) -> None: ...
    async def get_neighbors(
        self,
        node_id: uuid.UUID,
        *,
        direction: str = "out",
        relation: str | None = None,
    ) -> list[GraphNodeSchema]: ...
    async def get_path(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        max_depth: int = 6,
    ) -> list[GraphNodeSchema]: ...

    async def get_neighborhood(
        self,
        node_id: uuid.UUID,
        *,
        max_depth: int = 4,
        max_nodes: int = 100,
    ) -> tuple[list[GraphNodeSchema], list[GraphEdgeSchema]]: ...

    async def bulk_upsert_nodes(
        self,
        nodes: list[dict[str, Any]],
        *,
        repo_id: str,
        branch: str = "",
    ) -> dict[tuple[str, str], uuid.UUID]: ...

    async def bulk_upsert_edges(
        self,
        edges: list[dict[str, Any]],
        *,
        repo_id: str,
    ) -> int: ...

    async def list_repo_branches(self, repo_id: str) -> list[str]: ...


# ---------------------------------------------------------------------------
# Client Gateway Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IClientRepository(Protocol):
    async def create_client(self, **kwargs: Any) -> ClientSchema: ...
    async def get_client_by_id(self, client_id: uuid.UUID) -> ClientSchema | None: ...
    async def get_client_by_slug(self, slug: str) -> ClientSchema | None: ...
    async def list_clients(self) -> list[ClientSchema]: ...
    async def update_client(
        self, client_id: uuid.UUID, **kwargs: Any
    ) -> ClientSchema | None: ...
    async def create_client_api_key(self, **kwargs: Any) -> ClientApiKeySchema: ...
    async def list_client_api_keys(self, client_id: uuid.UUID) -> list[ClientApiKeySchema]: ...
    async def update_client_api_key(
        self, key_id: uuid.UUID, **kwargs: Any
    ) -> ClientApiKeySchema | None: ...
    async def create_client_session(self, **kwargs: Any) -> ClientSessionSchema: ...
    async def count_active_client_sessions(self) -> int: ...
    async def get_client_session_by_token_id(self, token_id: str) -> ClientSessionSchema | None: ...
    async def update_client_session(
        self, session_id: uuid.UUID, **kwargs: Any
    ) -> ClientSessionSchema | None: ...
    async def create_audit_log(self, **kwargs: Any) -> AuditLogSchema: ...
    async def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        event_type: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AuditLogSchema]: ...
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


@runtime_checkable
class IAdminJobRepository(Protocol):
    async def create_admin_job(self, **kwargs: Any) -> AdminJobSchema: ...
    async def get_admin_job_by_id(self, job_id: uuid.UUID) -> AdminJobSchema | None: ...
    async def list_admin_jobs(
        self,
        *,
        job_type: str | None = None,
        status: str | None = None,
        requested_by_user_id: uuid.UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AdminJobSchema]: ...
    async def update_admin_job(
        self, job_id: uuid.UUID, **kwargs: Any
    ) -> AdminJobSchema | None: ...


# ---------------------------------------------------------------------------
# Agent Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class IAgentRepository(Protocol):
    async def create_agent(self, **kwargs: Any) -> SubAgentSchema: ...
    async def get_agent_by_id(self, agent_id: uuid.UUID) -> SubAgentSchema | None: ...
    async def get_agent_by_name(self, name: str) -> SubAgentSchema | None: ...
    async def list_agents(
        self,
        *,
        workflow_step: str | None = None,
        tag: str | None = None,
        is_default: bool | None = None,
    ) -> list[SubAgentSchema]: ...
    async def upsert_agent(self, name: str, **kwargs: Any) -> SubAgentSchema: ...
    async def update_agent(self, agent_id: uuid.UUID, **kwargs: Any) -> SubAgentSchema | None: ...
    async def delete_agent(self, agent_id: uuid.UUID) -> None: ...


# ---------------------------------------------------------------------------
# Checkpoint Repository
# ---------------------------------------------------------------------------


@runtime_checkable
class ICheckpointRepository(Protocol):
    async def get_checkpoint(self, thread_id: str) -> dict[str, Any] | None: ...
    async def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        checkpoint: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
    async def list_checkpoints(
        self, thread_id: str, limit: int = 10
    ) -> list[dict[str, Any]]: ...


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
    IPromptRepository,
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
    IAdminJobRepository,
    IAgentRepository,
    ICheckpointRepository,
    Protocol,
):
    """
    Composite interface matching the current RelationalStore surface.

    This allows existing code that depends on a single store object
    (e.g., server.py, tools) to continue working while we migrate
    individual repositories to narrower interfaces.

    NOTE: New code should depend on the narrowest interface possible
    (e.g., IUserRepository) rather than IOperationalStore.
    """

    async def init_db(self) -> None: ...
    async def dispose(self) -> None: ...
