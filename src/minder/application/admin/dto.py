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
    # v2 — new node types
    "api_endpoint",
    "websocket_endpoint",
    "mq_producer",
    "mq_consumer",
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
    # v2 — new relation types
    "websocket",
    "cross_repo_calls",
    "exposes_websocket",
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
    actor_name: str | None  # display_name or slug for context
    event_type: str
    resource_type: str
    resource_id: str
    resource_name: str | None  # human-readable name for the resource
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


class SessionPayload(TypedDict):
    id: str
    user_id: str | None
    client_id: str | None
    name: str | None
    repo_id: str | None
    project_context: dict[str, Any]
    active_skills: dict[str, Any]
    state: dict[str, Any]
    ttl: int
    created_at: str
    last_active: str


class SessionListPayload(TypedDict):
    sessions: list[SessionPayload]


class SessionDetailPayload(TypedDict):
    session: SessionPayload


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
    clients: list[ClientPayload]  # MCP clients created by this user


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
    tracked_branches: list[str]
    workflow_name: str | None
    workflow_state: str | None
    current_step: str | None
    created_at: str | None


class RepositoryBranchPayload(TypedDict):
    branch: str
    is_default: bool
    last_synced: str | None
    payload_version: str | None
    source: str | None
    node_count: int
    edge_count: int
    deleted_nodes: int
    repo_path: str | None
    diff_base: str | None


class RepositoryBranchListPayload(TypedDict):
    repo_id: str
    default_branch: str | None
    tracked_branches: list[RepositoryBranchPayload]


class RepositoryBranchLinkPayload(TypedDict):
    id: str
    source_repo_id: str
    source_repo_name: str
    source_repo_url: str | None
    source_branch: str
    target_repo_id: str | None
    target_repo_name: str
    target_repo_url: str | None
    target_branch: str
    relation: str
    direction: str
    confidence: float
    last_seen_at: str | None
    source: str | None
    metadata: dict[str, Any]


class RepositoryBranchLinkListPayload(TypedDict):
    repo_id: str
    branch: str | None
    links: list[RepositoryBranchLinkPayload]


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
    last_sync: dict[str, Any] | None


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


class GraphSyncBranchLinkRequest(BaseModel):
    source_branch: str | None = None
    target_repo_id: str | None = None
    target_repo_name: str
    target_repo_url: str | None = None
    target_branch: str
    relation: str = "depends_on"
    direction: Literal["outbound", "inbound", "bidirectional"] = "outbound"
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphSyncRequest(BaseModel):
    payload_version: str
    source: str = "minder-cli"
    repo_path: str | None = None
    branch: str | None = None
    diff_base: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    commit_hash: str | None = None
    sync_metadata: dict[str, Any] = Field(default_factory=dict)
    nodes: list[GraphSyncNodeRequest] = Field(default_factory=list)
    edges: list[GraphSyncEdgeRequest] = Field(default_factory=list)
    branch_relationships: list[GraphSyncBranchLinkRequest] = Field(default_factory=list)


class UpsertRepositoryBranchLinkRequest(BaseModel):
    source_branch: str
    target_repo_id: str | None = None
    target_repo_name: str | None = None
    target_repo_url: str | None = None
    target_branch: str
    relation: str = "depends_on"
    direction: Literal["outbound", "inbound", "bidirectional"] = "outbound"
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class RepositoryGraphScopePayload(TypedDict):
    repo_id: str
    repo_name: str
    repo_path: str | None
    branch: str | None
    distance: int
    via_link: dict[str, Any] | None


class RepositoryGraphResultNodePayload(RepositoryGraphNodePayload, total=False):
    score: int
    direction: str
    distance: int
    repo_id: str
    repo_name: str
    branch: str | None
    landscape_distance: int
    via_link: dict[str, Any] | None


class RepositoryGraphEdgePayload(TypedDict):
    id: str
    source_id: str
    target_id: str
    relation: str
    weight: float


class RepositoryGraphSummaryPayload(TypedDict):
    repository: RepositoryPayload
    graph_available: bool
    active_branch: str | None
    branch_state: RepositoryBranchPayload | None
    branch_links: list[RepositoryBranchLinkPayload]
    last_sync: dict[str, Any] | None
    node_count: int
    counts_by_type: dict[str, int]
    routes: list[RepositoryGraphNodePayload]
    todos: list[RepositoryGraphNodePayload]
    external_services: list[RepositoryGraphNodePayload]
    dependencies: list[dict[str, Any]]


class RepositoryGraphSearchPayload(TypedDict):
    repository: RepositoryPayload
    active_branch: str | None
    query: str
    filters: dict[str, Any]
    scope_count: int
    searched_scopes: list[RepositoryGraphScopePayload]
    count: int
    results: list[RepositoryGraphResultNodePayload]


class RepositoryGraphImpactPayload(TypedDict):
    repository: RepositoryPayload
    active_branch: str | None
    target: str
    searched_scopes: list[RepositoryGraphScopePayload]
    matches: list[RepositoryGraphResultNodePayload]
    impacted: list[RepositoryGraphResultNodePayload]
    summary: dict[str, Any]


class RepositoryGraphMapPayload(TypedDict):
    repository: RepositoryPayload
    graph_available: bool
    branch: str | None
    branch_state: RepositoryBranchPayload | None
    branch_links: list[RepositoryBranchLinkPayload]
    nodes: list[RepositoryGraphNodePayload]
    edges: list[RepositoryGraphEdgePayload]
    summary: dict[str, Any]


class RepositoryLandscapeNodePayload(TypedDict):
    id: str
    repo_id: str
    repo_name: str
    branch: str
    remote_url: str | None
    is_default: bool
    last_synced: str | None


class RepositoryLandscapeEdgePayload(TypedDict):
    id: str
    source_id: str
    target_id: str
    relation: str
    direction: str
    confidence: float


class RepositoryLandscapePayload(TypedDict):
    repositories: list[RepositoryPayload]
    nodes: list[RepositoryLandscapeNodePayload]
    edges: list[RepositoryLandscapeEdgePayload]
    summary: dict[str, int]
