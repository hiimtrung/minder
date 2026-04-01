import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class SessionSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    repo_id: Optional[uuid.UUID] = None
    project_context: Dict[str, Any] = Field(default_factory=dict)
    active_skills: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    ttl: int = 3600
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    repo_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    project_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    active_skills: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    ttl: Mapped[int] = mapped_column(Integer, default=3600)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
