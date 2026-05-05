import uuid
from datetime import datetime, UTC
from typing import Any, List
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, String, DateTime, UUID, JSON, func, Text
from pydantic import Field

from .base import Base, BaseModelMeta


class SubAgentSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    title: str
    description: str
    system_prompt: str
    tools: List[str] = Field(default_factory=list)
    workflow_steps: List[str] = Field(default_factory=list)
    artifact_types: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SubAgent(Base):
    __tablename__ = "subagents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    tools: Mapped[List[Any]] = mapped_column(JSON, default=list)
    workflow_steps: Mapped[List[Any]] = mapped_column(JSON, default=list)
    artifact_types: Mapped[List[Any]] = mapped_column(JSON, default=list)
    tags: Mapped[List[Any]] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
