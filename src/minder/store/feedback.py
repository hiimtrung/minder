"""
FeedbackStore — async SQLAlchemy CRUD for the Feedback domain model.

Supports per-entity listing and rating aggregation.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from minder.models import Base, Feedback


class FeedbackStore:
    """Async store for :class:`~minder.models.Feedback` entities."""

    def __init__(self, db_url: str, echo: bool = False) -> None:
        self._engine = create_async_engine(db_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_feedback(self, **kwargs) -> Feedback:
        async with self._session() as sess:
            fb = Feedback(**kwargs)
            sess.add(fb)
            await sess.flush()
            await sess.refresh(fb)
            return fb

    async def get_feedback_by_id(self, feedback_id: uuid.UUID) -> Feedback | None:
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def list_feedback(self) -> list[Feedback]:
        async with self._session() as sess:
            result = await sess.execute(select(Feedback))
            return list(result.scalars().all())

    async def list_by_entity(
        self, entity_type: str, entity_id: uuid.UUID
    ) -> list[Feedback]:
        """Return all feedback for a specific entity."""
        async with self._session() as sess:
            result = await sess.execute(
                select(Feedback).where(
                    Feedback.entity_type == entity_type,
                    Feedback.entity_id == entity_id,
                )
            )
            return list(result.scalars().all())

    async def average_rating(self, entity_id: uuid.UUID) -> float | None:
        """
        Return the average rating across all feedback for ``entity_id``,
        or ``None`` if no feedback exists.
        """
        async with self._session() as sess:
            result = await sess.execute(
                select(func.avg(Feedback.rating)).where(
                    Feedback.entity_id == entity_id
                )
            )
            avg = result.scalar_one_or_none()
            return float(avg) if avg is not None else None

    async def update_feedback(self, feedback_id: uuid.UUID, **kwargs) -> Feedback | None:
        async with self._session() as sess:
            await sess.execute(
                update(Feedback).where(Feedback.id == feedback_id).values(**kwargs)
            )
            result = await sess.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            return result.scalar_one_or_none()

    async def delete_feedback(self, feedback_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Feedback).where(Feedback.id == feedback_id))
