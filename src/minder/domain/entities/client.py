import uuid
from datetime import UTC, datetime
from typing import Any
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class ClientSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    slug: str
    description: str = ""
    status: str = "active"
    created_by_user_id: uuid.UUID
    owner_team: str | None = None
    transport_modes: list[str] = Field(default_factory=lambda: ["sse", "stdio"])
    tool_scopes: list[str] = Field(default_factory=list)
    repo_scopes: list[str] = Field(default_factory=list)
    workflow_scopes: list[str] = Field(default_factory=list)
    rate_limit_policy: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ClientApiKeySchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    client_id: uuid.UUID
    key_prefix: str
    secret_hash: str
    status: str = "active"
    last_used_at: datetime | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

class ClientSessionSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    client_id: uuid.UUID
    access_token_id: str
    status: str = "active"
    scopes: list[str] = Field(default_factory=list)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    last_seen_at: datetime | None = None
    session_metadata: dict[str, Any] = Field(default_factory=dict)

class AuditLogSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    actor_type: str
    actor_id: str
    event_type: str
    resource_type: str
    resource_id: str | None = None
    request_id: str | None = None
    tool_name: str | None = None
    outcome: str = "success"
    ip: str | None = None
    user_agent: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
