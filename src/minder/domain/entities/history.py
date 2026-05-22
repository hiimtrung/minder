import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class HistorySchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: uuid.UUID
    role: str
    content: str
    reasoning_trace: Optional[str] = None
    tool_calls: Dict[str, Any] = Field(default_factory=dict)
    tokens_used: int = 0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
