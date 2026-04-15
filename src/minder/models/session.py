import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class SessionSchema(BaseModelMeta):
    """Pydantic schema for session serialisation / validation."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    # Owner — exactly one of user_id or client_id is set.
    user_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    # Human-readable project label for cross-environment lookup.
    name: Optional[str] = None
    repo_id: Optional[uuid.UUID] = None
    project_context: Dict[str, Any] = Field(default_factory=dict)
    active_skills: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    ttl: int = 86400  # 24 h default — long enough for multi-day work continuity
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Session(Base):
    """SQLAlchemy ORM model for the ``sessions`` table.

    Production store: MongoDB (``src/minder/store/mongodb/operational_store.py``).
    This SQLAlchemy model is retained for unit-test fixtures (SQLite in-memory)
    and is created fresh via ``Base.metadata.create_all`` — no migration needed.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    # Owner columns — mutually exclusive, both nullable.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # Optional project label — enables cross-environment lookup by name.
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    repo_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    project_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    active_skills: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    ttl: Mapped[int] = mapped_column(Integer, default=86400)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
