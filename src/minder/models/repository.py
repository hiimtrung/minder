import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class RepositorySchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_name: str
    repo_url: str
    default_branch: str
    tracked_branches: List[str] = Field(default_factory=list)
    workflow_id: Optional[uuid.UUID] = None
    state_path: str = ".minder"
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    relationships: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    repo_name: Mapped[str] = mapped_column(String, index=True)
    repo_url: Mapped[str] = mapped_column(String)
    default_branch: Mapped[str] = mapped_column(String)
    # v2: list of branches that have been synced/tracked (stored as JSON array)
    tracked_branches: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=True)
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    state_path: Mapped[str] = mapped_column(String, default=".minder")
    context_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    relationships: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class RepositoryWorkflowStateSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    repo_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    current_step: str
    completed_steps: List[str] = Field(default_factory=list)
    blocked_by: List[str] = Field(default_factory=list)
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RepositoryWorkflowState(Base):
    __tablename__ = "repository_workflow_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    current_step: Mapped[str] = mapped_column(String)
    completed_steps: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)  # stored as JSON list
    blocked_by: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)       # stored as JSON list
    artifacts: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    next_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
