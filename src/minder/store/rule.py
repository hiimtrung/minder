"""
RuleStore — async SQLAlchemy CRUD for the Rule domain model.

Supports filtering by scope and active flag.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from minder.models import Base, Rule


class RuleStore:
    """Async store for :class:`~minder.models.Rule` entities."""

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

    async def create_rule(self, **kwargs) -> Rule:
        async with self._session() as sess:
            rule = Rule(**kwargs)
            sess.add(rule)
            await sess.flush()
            await sess.refresh(rule)
            return rule

    async def get_rule_by_id(self, rule_id: uuid.UUID) -> Rule | None:
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            return result.scalar_one_or_none()

    async def list_rules(self) -> list[Rule]:
        async with self._session() as sess:
            result = await sess.execute(select(Rule))
            return list(result.scalars().all())

    async def list_by_scope(self, scope: str) -> list[Rule]:
        """Return all rules matching the given scope."""
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.scope == scope))
            return list(result.scalars().all())

    async def list_active(self) -> list[Rule]:
        """Return all active rules (active=True)."""
        async with self._session() as sess:
            result = await sess.execute(select(Rule).where(Rule.active.is_(True)))
            return list(result.scalars().all())

    async def update_rule(self, rule_id: uuid.UUID, **kwargs) -> Rule | None:
        async with self._session() as sess:
            await sess.execute(update(Rule).where(Rule.id == rule_id).values(**kwargs))
            result = await sess.execute(select(Rule).where(Rule.id == rule_id))
            return result.scalar_one_or_none()

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(delete(Rule).where(Rule.id == rule_id))
