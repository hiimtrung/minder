from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from minder.models.base import Base


class Checkpoint(Base):
    """
    LangGraph checkpoint data.
    """

    __tablename__ = "checkpoints"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), nullable=False
    )
