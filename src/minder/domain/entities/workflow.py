import uuid
from datetime import datetime, UTC
from typing import Dict, Any, List
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class WorkflowSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    description: str = ""
    enforcement: str = "strict"
    version: int = 1
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    policies: Dict[str, Any] = Field(default_factory=dict)
    default_for_repo: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
