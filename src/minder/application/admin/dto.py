from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

GraphSyncNodeType = Literal[
    "repository",
    "service",
    "module",
    "file",
    "function",
    "class",
    "interface",
    "abstract_class",
    "controller",
    "route",
    "todo",
    "external_service_api",
    "mq_topic",
]

GraphSyncRelationType = Literal[
    "contains",
    "imports",
    "depends_on",
    "calls",
    "implements",
    "extends",
    "exposes_route",
    "uses_external_service",
    "publishes",
    "consumes",
    "tracks",
]


class ClientPayload(TypedDict):
    id: str
    name: str
    slug: str
    description: str
    status: str
    tool_scopes: list[str]
    repo_scopes: list[str]
    workflow_scopes: list[str]
    transport_modes: list[str]


class ActivityEventPayload(TypedDict):
    event_type: str
    created_at: str


class AuditEventPayload(TypedDict):
    id: str
    actor_type: str
    actor_id: str
    actor_name: str | None        # display_name or slug for context
    event_type: str
    resource_type: str
    resource_id: str
    resource_name: str | None     # human-readable name for the resource
    outcome: str
    created_at: str | None


class ClientListPayload(TypedDict):
    clients: list[ClientPayload]


class CreateClientPayload(TypedDict):
    client: ClientPayload
    client_api_key: str


class ClientDetailPayload(TypedDict):
    client: ClientPayload


class OnboardingPayload(TypedDict):
    client: ClientPayload
    templates: dict[str, str]


class ClientConnectionTestPayload(TypedDict):
    ok: bool
    client: ClientPayload
    templates: dict[str, str]


class ClientKeyPayload(TypedDict):
    client_api_key: str


class RevokeKeysPayload(TypedDict):
    revoked: bool


class AuditListPayload(TypedDict):
    events: list[AuditEventPayload]
    total: int
    limit: int
    offset: int


class SetupResultPayload(TypedDict):
    api_key: str


class AdminLoginPayload(TypedDict):
    jwt: str


class AdminSessionPayload(TypedDict):
    id: str
    username: str
    email: str
    display_name: str
    role: str


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

class UserPayload(TypedDict):
    id: str
    username: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: str | None


class UserListPayload(TypedDict):
    users: list[UserPayload]


class UserDetailPayload(TypedDict):
    user: UserPayload
    clients: list[ClientPayload]   # MCP clients created by this user


class CreateUserPayload(TypedDict):
    user: UserPayload
    api_key: str


# ---------------------------------------------------------------------------
# Workflow management
# ---------------------------------------------------------------------------

class WorkflowStepPayload(TypedDict):
    name: str
    description: str
    gate: str | None


class WorkflowPayload(TypedDict):
    id: str
    name: str
    description: str
    enforcement: str
    steps: list[WorkflowStepPayload]
    created_at: str | None


class WorkflowListPayload(TypedDict):
    workflows: list[WorkflowPayload]


class WorkflowDetailPayload(TypedDict):
    workflow: WorkflowPayload


# ---------------------------------------------------------------------------
# Repository management
# ---------------------------------------------------------------------------

class RepositoryPayload(TypedDict):
    id: str
    name: str
    path: str
    remote_url: str | None
    default_branch: str | None
    workflow_name: str | None
    workflow_state: str | None
    current_step: str | None
    created_at: str | None


class RepositoryListPayload(TypedDict):
    repositories: list[RepositoryPayload]


class RepositoryDetailPayload(TypedDict):
    repository: RepositoryPayload


class UpdateRepositoryPayload(TypedDict, total=False):
    name: str
    remote_url: str | None
    default_branch: str | None
    path: str


class DeleteRepositoryPayload(TypedDict):
    deleted: bool


class ClientRepositoryResolveRequest(BaseModel):
    repo_name: str
    repo_path: str
    repo_url: str | None = None
    default_branch: str | None = None


class ClientRepositoryResolvePayload(TypedDict):
    repository: RepositoryPayload
    created: bool


class GraphSyncNodeRefRequest(BaseModel):
    node_type: GraphSyncNodeType
    name: str


class GraphSyncNodeRequest(BaseModel):
    node_type: GraphSyncNodeType
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphSyncEdgeRequest(BaseModel):
    source: GraphSyncNodeRefRequest
    target: GraphSyncNodeRefRequest
    relation: GraphSyncRelationType
    weight: float = 1.0


class GraphSyncRequest(BaseModel):
    payload_version: str
    source: str = "minder-cli"
    repo_path: str | None = None
    branch: str | None = None
    diff_base: str | None = None
    deleted_files: list[str] = Field(default_factory=list)
    sync_metadata: dict[str, Any] = Field(default_factory=dict)
    nodes: list[GraphSyncNodeRequest] = Field(default_factory=list)
    edges: list[GraphSyncEdgeRequest] = Field(default_factory=list)


class GraphSyncResultPayload(TypedDict):
    repo_id: str
    repository_name: str
    payload_version: str
    source: str
    branch: str | None
    deleted_nodes: int
    nodes_upserted: int
    edges_upserted: int
    accepted_at: str


class RepositoryGraphNodePayload(TypedDict):
    id: str
    node_type: str
    name: str
    metadata: dict[str, Any]


class RepositoryGraphEdgePayload(TypedDict):
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float


class RepositoryGraphSummaryPayload(TypedDict):
    repository: RepositoryPayload
    graph_available: bool
    last_sync: dict[str, Any] | None
    node_count: int
    counts_by_type: dict[str, int]
    routes: list[RepositoryGraphNodePayload]
    todos: list[RepositoryGraphNodePayload]
    external_services: list[RepositoryGraphNodePayload]
    dependencies: list[dict[str, Any]]


class RepositoryGraphSearchPayload(TypedDict):
    repository: RepositoryPayload
    query: str
    filters: dict[str, Any]
    count: int
    results: list[RepositoryGraphNodePayload]


class RepositoryGraphImpactPayload(TypedDict):
    repository: RepositoryPayload
    target: str
    matches: list[RepositoryGraphNodePayload]
    impacted: list[dict[str, Any]]
    summary: dict[str, Any]


class RepositoryGraphMapPayload(TypedDict):
    repository: RepositoryPayload
    graph_available: bool
    nodes: list[RepositoryGraphNodePayload]
    edges: list[RepositoryGraphEdgePayload]
    summary: dict[str, Any]
