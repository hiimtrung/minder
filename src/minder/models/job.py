import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, UUID, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base





class AdminJob(Base):
    __tablename__ = "admin_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    job_type: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True, default="queued")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    progress_current: Mapped[int] = mapped_column(default=0)
    progress_total: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
