import uuid
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, DateTime, UUID, JSON, func
from pydantic import Field

from .base import Base, BaseModelMeta

# Pydantic Schema
class UserSchema(BaseModelMeta):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    email: str
    username: str
    display_name: str
    api_key_hash: str
    # bcrypt/pbkdf2 hash of the login password; None means password login disabled
    password_hash: Optional[str] = None
    role: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login: Optional[datetime] = None

# SQLAlchemy Model
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[str] = mapped_column(String, index=True, default="default")
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    api_key_hash: Mapped[str] = mapped_column(String)
    # Optional bcrypt/pbkdf2 hash — null means only API-key auth available
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
