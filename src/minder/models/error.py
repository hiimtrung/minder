import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, UUID, JSON, func

from .base import Base



class Error(Base):
    __tablename__ = "errors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    error_code: Mapped[str] = mapped_column(String, index=True)
    error_message: Mapped[str] = mapped_column(String)
    stack_trace: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    resolution: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # vector as JSON fallback
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
