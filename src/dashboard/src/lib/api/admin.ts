export type ClientPayload = {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: string;
  tool_scopes: string[];
  repo_scopes: string[];
  workflow_scopes: string[];
  transport_modes: string[];
};

export type ClientListPayload = {
  clients: ClientPayload[];
};

export type ClientDetailPayload = {
  client: ClientPayload;
};

export type CreateClientPayload = {
  client: ClientPayload;
  client_api_key: string;
};

export type OnboardingPayload = {
  client: ClientPayload;
  templates: Record<string, string>;
};

export type AuditEventPayload = {
  id: string;
  actor_type: string;
  actor_id: string;
  actor_name: string | null;
  event_type: string;
  resource_type: string;
  resource_id: string | null;
  resource_name: string | null;
  outcome: string;
  created_at: string | null;
};

export type AuditListPayload = {
  events: AuditEventPayload[];
  total: number;
  limit: number;
  offset: number;
};

export type TokenExchangePayload = {
  access_token: string;
  token_type: "Bearer";
  client_id: string;
  scopes: string[];
  expires_at: string;
};

export type AdminSessionPayload = {
  id: string;
  username: string;
  email: string;
  display_name: string;
  role: string;
};

export type AdminSessionResponse = {
  admin: AdminSessionPayload;
};

export type DashboardBootstrapStatePayload = {
  has_admin_users: boolean;
  has_admin_session: boolean;
};

export type SetupAdminPayload = {
  api_key: string;
};

export type ToolInfo = {
  name: string;
  description: string;
};

export type ToolListPayload = {
  tools: ToolInfo[];
};

const API_BASE_URL = (import.meta.env.PUBLIC_API_URL ?? "")
  .trim()
  .replace(/\/$/, "");

function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const redirectOnUnauthorized =
    init?.headers instanceof Headers
      ? init.headers.get("X-Minder-Redirect-On-Unauthorized") !== "false"
      : typeof init?.headers === "object"
        ? (init?.headers as Record<string, string>)[
            "X-Minder-Redirect-On-Unauthorized"
          ] !== "false"
        : true;

  const headers = new Headers(init?.headers ?? {});
  headers.set("Content-Type", "application/json");
  headers.delete("X-Minder-Redirect-On-Unauthorized");

  const response = await fetch(apiUrl(path), {
    credentials: "include",
    headers,
    ...init,
  });

  if (!response.ok) {
    if (
      typeof window !== "undefined" &&
      response.status === 401 &&
      redirectOnUnauthorized
    ) {
      let next = window.location.pathname.startsWith("/dashboard/setup")
        ? "/dashboard/setup"
        : "/dashboard/login";
      try {
        const bootstrapResponse = await fetch(
          apiUrl("/v1/admin/bootstrap-state"),
          {
            credentials: "include",
          },
        );
        if (bootstrapResponse.ok) {
          const bootstrap =
            (await bootstrapResponse.json()) as DashboardBootstrapStatePayload;
          next = !bootstrap.has_admin_users
            ? "/dashboard/setup"
            : "/dashboard/login";
        }
      } catch {
        // Fall back to the default target when bootstrap-state cannot be read.
      }
      window.location.href = next;
    }
    let message = `Request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { error?: string };
      if (payload.error) {
        message = payload.error;
      }
    } catch {
      // Ignore JSON parse failures and fall back to status text.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function listClients(): Promise<ClientListPayload> {
  return requestJson<ClientListPayload>("/v1/admin/clients");
}

export async function setupAdmin(payload: {
  username: string;
  email: string;
  display_name: string;
  password?: string;
}): Promise<SetupAdminPayload> {
  return requestJson<SetupAdminPayload>("/v1/admin/setup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Login with username + password (preferred for human admins). */
export async function loginAdmin(credentials: {
  username: string;
  password: string;
}): Promise<{ ok: true }>;
/** Login with a raw API key (fallback / scripted access). */
export async function loginAdmin(credentials: {
  api_key: string;
}): Promise<{ ok: true }>;
export async function loginAdmin(
  credentials: { username: string; password: string } | { api_key: string },
): Promise<{ ok: true }> {
  return requestJson<{ ok: true }>("/v1/admin/login", {
    method: "POST",
    body: JSON.stringify(credentials),
    // Prevent the global 401 redirect so the login page can display the
    // error message instead of reloading.
    headers: { "X-Minder-Redirect-On-Unauthorized": "false" },
  });
}

export async function logoutAdmin(): Promise<{ ok: true }> {
  return requestJson<{ ok: true }>("/v1/admin/logout", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getAdminSession(): Promise<AdminSessionResponse> {
  return requestJson<AdminSessionResponse>("/v1/admin/session");
}

export async function getDashboardBootstrapState(): Promise<DashboardBootstrapStatePayload> {
  return requestJson<DashboardBootstrapStatePayload>(
    "/v1/admin/bootstrap-state",
    {
      headers: { "X-Minder-Redirect-On-Unauthorized": "false" },
    },
  );
}

export async function getClientDetail(
  clientId: string,
): Promise<ClientDetailPayload> {
  return requestJson<ClientDetailPayload>(`/v1/admin/clients/${clientId}`);
}

export async function createClient(payload: {
  name: string;
  slug: string;
  description?: string;
  tool_scopes?: string[];
  repo_scopes?: string[];
}): Promise<CreateClientPayload> {
  return requestJson<CreateClientPayload>("/v1/admin/clients", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getClientOnboarding(
  clientId: string,
): Promise<OnboardingPayload> {
  return requestJson<OnboardingPayload>(`/v1/admin/onboarding/${clientId}`);
}

export async function rotateClientKey(
  clientId: string,
): Promise<{ client_api_key: string }> {
  return requestJson<{ client_api_key: string }>(
    `/v1/admin/clients/${clientId}/keys`,
    {
      method: "POST",
      body: JSON.stringify({}),
      headers: { "X-Minder-Redirect-On-Unauthorized": "false" },
    },
  );
}

export async function revokeClientKeys(
  clientId: string,
): Promise<{ revoked: boolean }> {
  return requestJson<{ revoked: boolean }>(
    `/v1/admin/clients/${clientId}/keys/revoke`,
    {
      method: "POST",
      body: JSON.stringify({}),
      headers: { "X-Minder-Redirect-On-Unauthorized": "false" },
    },
  );
}

export async function testClientConnection(client_api_key: string): Promise<{
  ok: boolean;
  client: ClientPayload;
  templates: Record<string, string>;
}> {
  return requestJson(`/v1/gateway/test-connection`, {
    method: "POST",
    body: JSON.stringify({ client_api_key }),
    headers: { "X-Minder-Redirect-On-Unauthorized": "false" },
  });
}

export async function listTools(): Promise<ToolListPayload> {
  return requestJson<ToolListPayload>("/v1/admin/tools");
}

export async function updateClient(
  clientId: string,
  payload: {
    name?: string;
    description?: string;
    tool_scopes?: string[];
    repo_scopes?: string[];
  },
): Promise<ClientDetailPayload> {
  return requestJson<ClientDetailPayload>(`/v1/admin/clients/${clientId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listAudit(
  actorId?: string,
  limit = 50,
  offset = 0,
  eventType?: string,
  outcome?: string,
): Promise<AuditListPayload> {
  const params = new URLSearchParams();
  if (actorId) params.set("actor_id", actorId);
  if (eventType) params.set("event_type", eventType);
  if (outcome) params.set("outcome", outcome);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return requestJson<AuditListPayload>(`/v1/admin/audit?${params.toString()}`);
}

export async function exchangeClientKey(
  client_api_key: string,
): Promise<TokenExchangePayload> {
  return requestJson<TokenExchangePayload>("/v1/auth/token-exchange", {
    method: "POST",
    body: JSON.stringify({ client_api_key }),
  });
}

// ---------------------------------------------------------------------------
// User management
// ---------------------------------------------------------------------------

export type UserPayload = {
  id: string;
  username: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
};

export type UserListPayload = { users: UserPayload[] };
export type UserDetailPayload = { user: UserPayload; clients: ClientPayload[] };
export type CreateUserPayload = { user: UserPayload; api_key: string };

export async function createUser(payload: {
  username: string;
  email: string;
  display_name: string;
  role?: string;
  password?: string;
}): Promise<CreateUserPayload> {
  return requestJson<CreateUserPayload>("/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listUsers(activeOnly = false): Promise<UserListPayload> {
  const query = activeOnly ? "?active_only=true" : "";
  return requestJson<UserListPayload>(`/v1/admin/users${query}`);
}

export async function getUserDetail(
  userId: string,
): Promise<UserDetailPayload> {
  return requestJson<UserDetailPayload>(`/v1/admin/users/${userId}`);
}

export async function updateUser(
  userId: string,
  payload: { role?: string; is_active?: boolean; display_name?: string },
): Promise<UserDetailPayload> {
  return requestJson<UserDetailPayload>(`/v1/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deactivateUser(
  userId: string,
): Promise<UserDetailPayload> {
  return requestJson<UserDetailPayload>(`/v1/admin/users/${userId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Workflow management
// ---------------------------------------------------------------------------

export type WorkflowStepPayload = {
  name: string;
  description: string;
  gate: string | null;
};

export type WorkflowPayload = {
  id: string;
  name: string;
  description: string;
  enforcement: string;
  steps: WorkflowStepPayload[];
  created_at: string | null;
};

export type WorkflowListPayload = { workflows: WorkflowPayload[] };
export type WorkflowDetailPayload = { workflow: WorkflowPayload };

export async function listWorkflows(): Promise<WorkflowListPayload> {
  return requestJson<WorkflowListPayload>("/v1/admin/workflows");
}

export async function getWorkflowDetail(
  workflowId: string,
): Promise<WorkflowDetailPayload> {
  return requestJson<WorkflowDetailPayload>(
    `/v1/admin/workflows/${workflowId}`,
  );
}

export async function createWorkflow(payload: {
  name: string;
  description?: string;
  enforcement?: string;
  steps?: WorkflowStepPayload[];
}): Promise<WorkflowDetailPayload> {
  return requestJson<WorkflowDetailPayload>("/v1/admin/workflows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWorkflow(
  workflowId: string,
  payload: {
    name?: string;
    description?: string;
    enforcement?: string;
    steps?: WorkflowStepPayload[];
  },
): Promise<WorkflowDetailPayload> {
  return requestJson<WorkflowDetailPayload>(
    `/v1/admin/workflows/${workflowId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteWorkflow(
  workflowId: string,
): Promise<{ deleted: boolean }> {
  return requestJson<{ deleted: boolean }>(
    `/v1/admin/workflows/${workflowId}`,
    {
      method: "DELETE",
    },
  );
}

// ---------------------------------------------------------------------------
// Repository management
// ---------------------------------------------------------------------------

export type RepositoryPayload = {
  id: string;
  name: string;
  path: string;
  remote_url: string | null;
  default_branch: string | null;
  tracked_branches: string[];
  workflow_name: string | null;
  workflow_state: string | null;
  current_step: string | null;
  created_at: string | null;
};

export type RepositoryListPayload = { repositories: RepositoryPayload[] };
export type RepositoryDetailPayload = { repository: RepositoryPayload };
export type DeleteRepositoryPayload = { deleted: boolean };

export async function listRepositories(): Promise<RepositoryListPayload> {
  return requestJson<RepositoryListPayload>("/v1/admin/repositories");
}

export async function getRepositoryDetail(
  repoId: string,
): Promise<RepositoryDetailPayload> {
  return requestJson<RepositoryDetailPayload>(
    `/v1/admin/repositories/${repoId}`,
  );
}

export async function updateRepository(
  repoId: string,
  payload: {
    name?: string;
    remote_url?: string | null;
    default_branch?: string | null;
    path?: string;
  },
): Promise<RepositoryDetailPayload> {
  return requestJson<RepositoryDetailPayload>(
    `/v1/admin/repositories/${repoId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteRepository(
  repoId: string,
): Promise<DeleteRepositoryPayload> {
  return requestJson<DeleteRepositoryPayload>(
    `/v1/admin/repositories/${repoId}`,
    {
      method: "DELETE",
    },
  );
}

export type RepositoryGraphNodePayload = {
  id: string;
  node_type: string;
  name: string;
  metadata: Record<string, unknown>;
};

export type RepositoryGraphEdgePayload = {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  weight: number;
};

export type RepositoryGraphDependencyPayload = {
  service: string;
  depends_on: Array<{
    id: string;
    name: string;
    node_type: string;
  }>;
};

export type RepositoryGraphSummaryPayload = {
  repository: RepositoryPayload;
  graph_available: boolean;
  active_branch: string | null;
  branch_state: RepositoryBranchPayload | null;
  branch_links: RepositoryBranchLinkPayload[];
  last_sync: Record<string, unknown> | null;
  node_count: number;
  counts_by_type: Record<string, number>;
  routes: RepositoryGraphNodePayload[];
  todos: RepositoryGraphNodePayload[];
  external_services: RepositoryGraphNodePayload[];
  dependencies: RepositoryGraphDependencyPayload[];
};

export type RepositoryGraphScopePayload = {
  repo_id: string;
  repo_name: string;
  repo_path: string | null;
  branch: string | null;
  distance: number;
  via_link: Record<string, unknown> | null;
};

export type RepositoryGraphResultNodePayload = RepositoryGraphNodePayload & {
  score?: number;
  direction?: string;
  distance?: number;
  repo_id?: string;
  repo_name?: string;
  branch?: string | null;
  landscape_distance?: number;
  via_link?: Record<string, unknown> | null;
};

export type RepositoryGraphSearchPayload = {
  repository: RepositoryPayload;
  active_branch: string | null;
  query: string;
  filters: {
    node_types?: string[];
    languages?: string[];
    last_states?: string[];
  };
  scope_count: number;
  searched_scopes: RepositoryGraphScopePayload[];
  count: number;
  results: RepositoryGraphResultNodePayload[];
};

export type RepositoryGraphImpactPayload = {
  repository: RepositoryPayload;
  active_branch: string | null;
  target: string;
  searched_scopes: RepositoryGraphScopePayload[];
  matches: RepositoryGraphResultNodePayload[];
  impacted: RepositoryGraphResultNodePayload[];
  summary: Record<string, number | Record<string, number>>;
};

export type RepositoryGraphMapPayload = {
  repository: RepositoryPayload;
  graph_available: boolean;
  branch: string | null;
  branch_state: RepositoryBranchPayload | null;
  branch_links: RepositoryBranchLinkPayload[];
  nodes: RepositoryGraphNodePayload[];
  edges: RepositoryGraphEdgePayload[];
  summary: {
    node_count: number;
    edge_count: number;
    counts_by_type: Record<string, number>;
    counts_by_relation: Record<string, number>;
  };
};

export type RepositoryBranchPayload = {
  branch: string;
  is_default: boolean;
  last_synced: string | null;
  payload_version: string | null;
  source: string | null;
  node_count: number;
  edge_count: number;
  deleted_nodes: number;
  repo_path: string | null;
  diff_base: string | null;
};

export type RepositoryBranchListPayload = {
  repo_id: string;
  default_branch: string | null;
  tracked_branches: RepositoryBranchPayload[];
};

export type RepositoryBranchLinkPayload = {
  id: string;
  source_repo_id: string;
  source_repo_name: string;
  source_repo_url: string | null;
  source_branch: string;
  target_repo_id: string | null;
  target_repo_name: string;
  target_repo_url: string | null;
  target_branch: string;
  relation: string;
  direction: string;
  confidence: number;
  last_seen_at: string | null;
  source: string | null;
  metadata: Record<string, unknown>;
};

export type RepositoryBranchLinkListPayload = {
  repo_id: string;
  branch: string | null;
  links: RepositoryBranchLinkPayload[];
};

export type RepositoryLandscapeNodePayload = {
  id: string;
  repo_id: string;
  repo_name: string;
  branch: string;
  remote_url: string | null;
  is_default: boolean;
  last_synced: string | null;
};

export type RepositoryLandscapeEdgePayload = {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  direction: string;
  confidence: number;
};

export type RepositoryLandscapePayload = {
  repositories: RepositoryPayload[];
  nodes: RepositoryLandscapeNodePayload[];
  edges: RepositoryLandscapeEdgePayload[];
  summary: {
    repo_count: number;
    branch_count: number;
    link_count: number;
  };
};

export async function getRepositoryBranches(
  repoId: string,
): Promise<RepositoryBranchListPayload> {
  return requestJson<RepositoryBranchListPayload>(
    `/v1/admin/repositories/${repoId}/branches`,
  );
}

export async function addRepositoryBranch(
  repoId: string,
  branch: string,
): Promise<RepositoryBranchListPayload> {
  return requestJson<RepositoryBranchListPayload>(
    `/v1/admin/repositories/${repoId}/branches`,
    { method: "POST", body: JSON.stringify({ branch }) },
  );
}

export async function removeRepositoryBranch(
  repoId: string,
  branch: string,
): Promise<RepositoryBranchListPayload> {
  return requestJson<RepositoryBranchListPayload>(
    `/v1/admin/repositories/${repoId}/branches/${encodeURIComponent(branch)}`,
    { method: "DELETE" },
  );
}

export async function getRepositoryBranchLinks(
  repoId: string,
  branch?: string,
): Promise<RepositoryBranchLinkListPayload> {
  const params = new URLSearchParams();
  if (branch) params.set("branch", branch);
  const qs = params.toString();
  return requestJson<RepositoryBranchLinkListPayload>(
    `/v1/admin/repositories/${repoId}/branch-links${qs ? `?${qs}` : ""}`,
  );
}

export async function upsertRepositoryBranchLink(
  repoId: string,
  payload: {
    source_branch: string;
    target_repo_id?: string | null;
    target_repo_name?: string | null;
    target_repo_url?: string | null;
    target_branch: string;
    relation?: string;
    direction?: "outbound" | "inbound" | "bidirectional";
    confidence?: number;
    metadata?: Record<string, unknown>;
  },
): Promise<RepositoryBranchLinkListPayload> {
  return requestJson<RepositoryBranchLinkListPayload>(
    `/v1/admin/repositories/${repoId}/branch-links`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteRepositoryBranchLink(
  repoId: string,
  linkId: string,
  branch?: string,
): Promise<RepositoryBranchLinkListPayload> {
  const params = new URLSearchParams();
  if (branch) params.set("branch", branch);
  const qs = params.toString();
  return requestJson<RepositoryBranchLinkListPayload>(
    `/v1/admin/repositories/${repoId}/branch-links/${encodeURIComponent(linkId)}${qs ? `?${qs}` : ""}`,
    {
      method: "DELETE",
    },
  );
}

export async function getRepositoryLandscape(): Promise<RepositoryLandscapePayload> {
  return requestJson<RepositoryLandscapePayload>(
    "/v1/admin/repositories/landscape",
  );
}

export async function getRepositoryGraphMap(
  repoId: string,
  branch?: string,
): Promise<RepositoryGraphMapPayload> {
  const params = new URLSearchParams();
  if (branch) params.set("branch", branch);
  const qs = params.toString();
  return requestJson<RepositoryGraphMapPayload>(
    `/v1/admin/repositories/${repoId}/graph-map${qs ? `?${qs}` : ""}`,
  );
}

export async function getRepositoryGraphSummary(
  repoId: string,
  branch?: string,
): Promise<RepositoryGraphSummaryPayload> {
  const params = new URLSearchParams();
  if (branch) params.set("branch", branch);
  const qs = params.toString();
  return requestJson<RepositoryGraphSummaryPayload>(
    `/v1/admin/repositories/${repoId}/graph-summary${qs ? `?${qs}` : ""}`,
  );
}

export async function searchRepositoryGraph(
  repoId: string,
  options: {
    query: string;
    branch?: string;
    nodeTypes?: string[];
    languages?: string[];
    lastStates?: string[];
    limit?: number;
  },
): Promise<RepositoryGraphSearchPayload> {
  const params = new URLSearchParams();
  params.set("query", options.query);
  params.set("limit", String(options.limit ?? 10));
  if (options.branch) params.set("branch", options.branch);
  for (const nodeType of options.nodeTypes ?? []) {
    params.append("node_type", nodeType);
  }
  for (const language of options.languages ?? []) {
    params.append("language", language);
  }
  for (const lastState of options.lastStates ?? []) {
    params.append("last_state", lastState);
  }
  return requestJson<RepositoryGraphSearchPayload>(
    `/v1/admin/repositories/${repoId}/graph-search?${params.toString()}`,
  );
}

export async function getRepositoryGraphImpact(
  repoId: string,
  target: string,
  depth = 2,
  limit = 25,
  branch?: string,
): Promise<RepositoryGraphImpactPayload> {
  const params = new URLSearchParams({
    target,
    depth: String(depth),
    limit: String(limit),
  });
  if (branch) params.set("branch", branch);
  return requestJson<RepositoryGraphImpactPayload>(
    `/v1/admin/repositories/${repoId}/graph-impact?${params.toString()}`,
  );
}

// ---------------------------------------------------------------------------
// Observability
// ---------------------------------------------------------------------------

export type MetricsBucket = {
  total: number;
  by_outcome?: Record<string, number>;
  by_type?: Record<string, number>;
  by_status?: Record<string, number>;
};

export type MetricsSummaryPayload = {
  active_client_sessions: number;
  tool_calls: { total: number; by_outcome: Record<string, number> };
  auth_events: { total: number; by_type: Record<string, number> };
  http_requests: { total: number; by_status: Record<string, number> };
  admin_operations: { total: number; by_outcome: Record<string, number> };
};

export async function getMetricsSummary(
  client_id?: string,
  event_type?: string,
  outcome?: string,
): Promise<MetricsSummaryPayload> {
  const params = new URLSearchParams();
  if (client_id) params.set("client_id", client_id);
  if (event_type) params.set("event_type", event_type);
  if (outcome) params.set("outcome", outcome);

  const query = params.toString();
  const path = query
    ? `/v1/admin/metrics-summary?${query}`
    : "/v1/admin/metrics-summary";
  return requestJson<MetricsSummaryPayload>(path);
}
