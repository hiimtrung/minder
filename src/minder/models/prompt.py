import uuid
from datetime import datetime, UTC
from typing import List
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, UUID, JSON, Text, func
from pydantic import Field

from .base import Base, BaseModelMeta


# Pydantic Schema
class PromptSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    title: str
    description: str
    content_template: str
    arguments: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# SQLAlchemy Model
class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    content_template: Mapped[str] = mapped_column(Text)
    arguments: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
