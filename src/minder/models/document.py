import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, UUID, JSON, func

from .base import Base



class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String, index=True)
    source_path: Mapped[str] = mapped_column(String)
    chunks: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    project: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
