import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, UUID, JSON, func

from .base import Base




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
