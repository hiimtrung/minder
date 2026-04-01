from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from minder.models.history import History
from minder.models.session import Session
from minder.store.relational import RelationalStore


class HistoryStore:
    def __init__(self, store: RelationalStore) -> None:
        self._store = store

    async def create_history(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        reasoning_trace: str | None = None,
        tool_calls: dict[str, Any] | None = None,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> History:
        async with self._store._session() as sess:
            history = History(
                id=uuid.uuid4(),
                session_id=session_id,
                role=role,
                content=content,
                reasoning_trace=reasoning_trace,
                tool_calls=tool_calls or {},
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )
            sess.add(history)
            await sess.flush()
            await sess.refresh(history)
            return history

    async def list_history_for_session(self, session_id: uuid.UUID) -> list[History]:
        async with self._store._session() as sess:
            result = await sess.execute(
                select(History).where(History.session_id == session_id)
            )
            return list(result.scalars().all())

    async def list_history_for_user(self, user_id: uuid.UUID) -> list[History]:
        async with self._store._session() as sess:
            result = await sess.execute(
                select(History)
                .join(Session, Session.id == History.session_id)
                .where(Session.user_id == user_id)
            )
            return list(result.scalars().all())
