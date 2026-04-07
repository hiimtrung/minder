import uuid
from datetime import datetime, UTC
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON, String, Boolean, Integer, DateTime, UUID, func
from pydantic import Field

from .base import Base, BaseModelMeta


class RuleSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: str
    pattern: str
    content: str
    priority: int = 0
    scope: str  # enum: global, project, language, repository
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    pattern: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(String, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_type: str  # enum: skill, response, retrieval, workflow
    entity_id: uuid.UUID
    rating: int  # 1 to 5
    feedback_text: str = ""
    context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Feedback(Base):
    """SQLAlchemy ORM model for user/system feedback on entities."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    feedback_text: Mapped[str] = mapped_column(String, default="")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetadataSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_type: str  # enum: skill, history, error, document, workflow
    entity_id: uuid.UUID
    key: str
    value: dict = Field(default_factory=dict)
    source: str  # enum: user, system, import
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
