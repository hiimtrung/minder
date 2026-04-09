from __future__ import annotations

from typing import TypedDict


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
    event_type: str
    resource_type: str
    resource_id: str
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
