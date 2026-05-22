import uuid
from datetime import datetime, UTC
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class RuleSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: str
    pattern: str
    content: str
    priority: int = 0
    scope: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class FeedbackSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_type: str
    entity_id: uuid.UUID
    rating: int
    feedback_text: str = ""
    context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class MetadataSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    entity_type: str
    entity_id: uuid.UUID
    key: str
    value: dict = Field(default_factory=dict)
    source: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
