import uuid
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Integer, DateTime, UUID, JSON, func

from .base import Base



class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(String, default="")
    enforcement: Mapped[str] = mapped_column(String, default="strict")
    version: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)  # list of step dicts
    policies: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    default_for_repo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
