import uuid
from datetime import datetime, UTC
from typing import List
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class PromptSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    title: str
    description: str
    content_template: str
    arguments: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
