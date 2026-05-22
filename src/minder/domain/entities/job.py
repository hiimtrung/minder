import uuid
from datetime import UTC, datetime
from typing import Any
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class AdminJobSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    job_type: str
    title: str
    status: str = "queued"
    requested_by_user_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    message: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
