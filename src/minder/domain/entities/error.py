import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class ErrorSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    error_code: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    resolution: Optional[str] = None
    embedding: Optional[List[float]] = None
    resolved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
