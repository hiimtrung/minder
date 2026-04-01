import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

class HistorySchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: uuid.UUID
    role: str  # enum: user, assistant, system, tool
    content: str
    reasoning_trace: Optional[str] = None
    tool_calls: Dict[str, Any] = Field(default_factory=dict)  # JSON list of tool calls
    tokens_used: int = 0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class History(Base):
    __tablename__ = "history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    reasoning_trace: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tool_calls: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
