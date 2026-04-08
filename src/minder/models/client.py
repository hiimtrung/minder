import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import Field
from sqlalchemy import DateTime, JSON, String, UUID, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, BaseModelMeta


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


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="active")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    owner_team: Mapped[str | None] = mapped_column(String, nullable=True)
    transport_modes: Mapped[list[str]] = mapped_column(JSON, default=list)
    tool_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    repo_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    workflow_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    rate_limit_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ClientApiKey(Base):
    __tablename__ = "client_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    key_prefix: Mapped[str] = mapped_column(String, index=True)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientSession(Base):
    __tablename__ = "client_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    access_token_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, default="active")
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_type: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    resource_type: Mapped[str] = mapped_column(String, index=True)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String, default="success")
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
