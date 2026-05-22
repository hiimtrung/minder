import uuid
from datetime import datetime, UTC
from typing import List
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class SubAgentSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    title: str
    description: str
    system_prompt: str
    tools: List[str] = Field(default_factory=list)
    workflow_steps: List[str] = Field(default_factory=list)
    artifact_types: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_default: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
