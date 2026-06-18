import uuid
from datetime import datetime
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class MaintenanceJobSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    schedule: str
    enabled: bool = True
    require_idle: bool = True
    max_runtime_s: int = 120
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_summary: str | None = None

class MaintenanceRunSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    job_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    duration_s: float | None = None
    mode: str
    summary: str | None = None
    error_message: str | None = None
