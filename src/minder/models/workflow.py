import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Integer, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class WorkflowSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    version: int = 1
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    policies: Dict[str, Any] = Field(default_factory=dict)
    default_for_repo: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)  # list of step dicts
    policies: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    default_for_repo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
