import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, String, UUID, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class MaintenanceJob(Base):
    __tablename__ = "maintenance_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    schedule: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    require_idle: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    max_runtime_s: Mapped[int] = mapped_column(default=120)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_summary: Mapped[str | None] = mapped_column(String, nullable=True)

class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_name: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
