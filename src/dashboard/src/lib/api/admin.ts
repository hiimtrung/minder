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
  event_type: string;
  resource_type: string;
  resource_id: string;
  outcome: string;
  created_at: string | null;
};

export type AuditListPayload = {
  events: AuditEventPayload[];
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

export type SetupAdminPayload = {
  api_key: string;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    if (typeof window !== "undefined" && response.status === 401) {
      const next = window.location.pathname.startsWith("/dashboard/setup")
        ? "/dashboard/setup"
        : "/dashboard/login";
      window.location.href = next;
    }
    throw new Error(`Request failed: ${response.status}`);
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
}): Promise<SetupAdminPayload> {
  return requestJson<SetupAdminPayload>("/v1/admin/setup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginAdmin(api_key: string): Promise<{ ok: true }> {
  return requestJson<{ ok: true }>("/v1/admin/login", {
    method: "POST",
    body: JSON.stringify({ api_key }),
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

export async function getClientDetail(clientId: string): Promise<ClientDetailPayload> {
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

export async function getClientOnboarding(clientId: string): Promise<OnboardingPayload> {
  return requestJson<OnboardingPayload>(`/v1/admin/onboarding/${clientId}`);
}

export async function rotateClientKey(clientId: string): Promise<{ client_api_key: string }> {
  return requestJson<{ client_api_key: string }>(`/v1/admin/clients/${clientId}/keys`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function revokeClientKeys(clientId: string): Promise<{ revoked: boolean }> {
  return requestJson<{ revoked: boolean }>(`/v1/admin/clients/${clientId}/keys/revoke`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function testClientConnection(client_api_key: string): Promise<{
  ok: boolean;
  client: ClientPayload;
  templates: Record<string, string>;
}> {
  return requestJson(`/v1/gateway/test-connection`, {
    method: "POST",
    body: JSON.stringify({ client_api_key }),
  });
}

export async function listAudit(actorId?: string): Promise<AuditListPayload> {
  const query = actorId ? `?actor_id=${encodeURIComponent(actorId)}` : "";
  return requestJson<AuditListPayload>(`/v1/admin/audit${query}`);
}

export async function exchangeClientKey(client_api_key: string): Promise<TokenExchangePayload> {
  return requestJson<TokenExchangePayload>("/v1/auth/token-exchange", {
    method: "POST",
    body: JSON.stringify({ client_api_key }),
  });
}
