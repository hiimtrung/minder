import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

# Pydantic Schema
class SkillSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    content: str
    language: str
    tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None  # vector(default 768) stored as JSON list
    usage_count: int = 0
    quality_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# SQLAlchemy Model
class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    title: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String, index=True)
    tags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
    # Embedding stored as JSON list for cross-dialect compatibility (SQLite dev / PostgreSQL prod)
    embedding: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
