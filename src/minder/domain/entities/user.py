import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from pydantic import Field
from minder.domain.entities.base import BaseModelMeta

class UserSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    email: str
    username: str
    display_name: str
    api_key_hash: str
    password_hash: Optional[str] = None
    role: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login: Optional[datetime] = None
