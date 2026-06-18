import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, String, Integer, Float, DateTime, UUID, JSON, func

from .base import Base





# SQLAlchemy Model
class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    title: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String, index=True)
    tags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
    # Embedding stored as JSON list for cross-dialect compatibility (SQLite dev / PostgreSQL prod)
    embedding: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    source_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    excerpt_kind: Mapped[str] = mapped_column(String, default="none")
    status: Mapped[str] = mapped_column(String, default="active", server_default="active")
    review_proposal: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Multi-developer isolation: owner_id is the principal who created this entry.
    # None means team/legacy (visible to all). Indexed for efficient filtering.
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # 'private' = only visible to owner, 'team' = visible to all principals
    scope: Mapped[str] = mapped_column(String, default="private", server_default="private")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
