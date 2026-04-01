import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class DocumentSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    content: str
    doc_type: str  # enum: markdown, code, api_spec, config
    source_path: str
    chunks: Dict[str, Any] = Field(default_factory=dict)  # JSON list of chunks
    embedding: Optional[List[float]] = None  # vector(1024) stored as JSON list
    project: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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
