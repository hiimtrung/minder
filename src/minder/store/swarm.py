"""Dedicated store for swarm coordination state (decision Q3 — separate ``swarm.db``).

Owns its own async engine and connection pool. High-frequency heartbeat writes
here never contend with the operational store's graph/memory queries.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from minder.domain.entities.swarm import (
    HandoffSchema,
    SwarmManifestSchema,
    SwarmNodeSchema,
    SwarmSchema,
    SwarmTaskSchema,
)
from minder.models.swarm import Handoff, Swarm, SwarmBase, SwarmManifest, SwarmNode, SwarmTask


def _to_url(raw_path: str) -> str:
    db_path = Path(raw_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


class SwarmStore:
    """Async SQLAlchemy store backed by a dedicated swarm.db SQLite file."""

    def __init__(self, db_path: str = "~/.minder/data/swarm.db", echo: bool = False) -> None:
        url = _to_url(db_path)
        self._engine: AsyncEngine = create_async_engine(
            url, echo=echo, connect_args={"timeout": 30}
        )
        self._configure_sqlite(self._engine)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )
        self._initialized = False
        self._init_lock: Any = None

    @staticmethod
    def _configure_sqlite(engine: AsyncEngine) -> None:
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:  # noqa: ANN401
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    async def init_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(SwarmBase.metadata.create_all)
        self._initialized = True

    async def _ensure_init(self) -> None:
        """Lazy idempotent init so a store constructed outside the lifespan still works."""
        if self._initialized:
            return
        import asyncio

        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if not self._initialized:
                await self.init_db()

    async def dispose(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._initialized:
            await self._ensure_init()
        async with self._session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    # ── Swarms ──────────────────────────────────────────────────────────────
    async def create_swarm(self, **kwargs: Any) -> SwarmSchema:
        async with self._session() as sess:
            item = Swarm(**kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return SwarmSchema.model_validate(item)

    async def get_swarm(self, swarm_id: uuid.UUID) -> SwarmSchema | None:
        async with self._session() as sess:
            res = await sess.execute(select(Swarm).where(Swarm.id == swarm_id))
            item = res.scalar_one_or_none()
            return SwarmSchema.model_validate(item) if item else None

    async def update_swarm(self, swarm_id: uuid.UUID, **kwargs: Any) -> SwarmSchema | None:
        async with self._session() as sess:
            await sess.execute(update(Swarm).where(Swarm.id == swarm_id).values(**kwargs))
            res = await sess.execute(select(Swarm).where(Swarm.id == swarm_id))
            item = res.scalar_one_or_none()
            return SwarmSchema.model_validate(item) if item else None

    async def list_swarms(self) -> list[SwarmSchema]:
        async with self._session() as sess:
            res = await sess.execute(select(Swarm).order_by(Swarm.created_at.desc()))
            return [SwarmSchema.model_validate(i) for i in res.scalars().all()]

    # ── Nodes (presence) ────────────────────────────────────────────────────
    async def create_node(self, **kwargs: Any) -> SwarmNodeSchema:
        async with self._session() as sess:
            item = SwarmNode(last_heartbeat_at=datetime.now(UTC), **kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return SwarmNodeSchema.model_validate(item)

    async def update_node(self, node_id: uuid.UUID, **kwargs: Any) -> SwarmNodeSchema | None:
        async with self._session() as sess:
            await sess.execute(update(SwarmNode).where(SwarmNode.id == node_id).values(**kwargs))
            res = await sess.execute(select(SwarmNode).where(SwarmNode.id == node_id))
            item = res.scalar_one_or_none()
            return SwarmNodeSchema.model_validate(item) if item else None

    async def heartbeat(self, node_id: uuid.UUID, status: str | None = None) -> SwarmNodeSchema | None:
        values: dict[str, Any] = {"last_heartbeat_at": datetime.now(UTC)}
        if status:
            values["status"] = status
        return await self.update_node(node_id, **values)

    async def list_nodes(self, swarm_id: uuid.UUID) -> list[SwarmNodeSchema]:
        async with self._session() as sess:
            res = await sess.execute(select(SwarmNode).where(SwarmNode.swarm_id == swarm_id))
            return [SwarmNodeSchema.model_validate(i) for i in res.scalars().all()]

    async def reap_dead_nodes(self, swarm_id: uuid.UUID, ttl_seconds: int) -> list[uuid.UUID]:
        """Mark nodes whose heartbeat expired as ``dead`` and release their claims.

        Returns the list of task ids whose claims were released so the caller can
        reset those tasks back to ``ready``.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
        released: list[uuid.UUID] = []
        async with self._session() as sess:
            res = await sess.execute(
                select(SwarmNode).where(
                    SwarmNode.swarm_id == swarm_id,
                    SwarmNode.status != "dead",
                    SwarmNode.status != "done",
                )
            )
            for node in res.scalars().all():
                hb = node.last_heartbeat_at
                if hb is None:
                    continue
                if hb.tzinfo is None:
                    hb = hb.replace(tzinfo=UTC)
                if hb < cutoff:
                    node.status = "dead"
                    if node.current_task_id:
                        released.append(node.current_task_id)
        return released

    # ── Tasks (board) ───────────────────────────────────────────────────────
    async def create_task(self, **kwargs: Any) -> SwarmTaskSchema:
        async with self._session() as sess:
            item = SwarmTask(**kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return SwarmTaskSchema.model_validate(item)

    async def get_task(self, task_id: uuid.UUID) -> SwarmTaskSchema | None:
        async with self._session() as sess:
            res = await sess.execute(select(SwarmTask).where(SwarmTask.id == task_id))
            item = res.scalar_one_or_none()
            return SwarmTaskSchema.model_validate(item) if item else None

    async def list_tasks(self, swarm_id: uuid.UUID) -> list[SwarmTaskSchema]:
        async with self._session() as sess:
            res = await sess.execute(
                select(SwarmTask).where(SwarmTask.swarm_id == swarm_id).order_by(SwarmTask.created_at)
            )
            return [SwarmTaskSchema.model_validate(i) for i in res.scalars().all()]

    async def update_task(self, task_id: uuid.UUID, **kwargs: Any) -> SwarmTaskSchema | None:
        async with self._session() as sess:
            await sess.execute(update(SwarmTask).where(SwarmTask.id == task_id).values(**kwargs))
            res = await sess.execute(select(SwarmTask).where(SwarmTask.id == task_id))
            item = res.scalar_one_or_none()
            return SwarmTaskSchema.model_validate(item) if item else None

    async def claim_task(
        self, task_id: uuid.UUID, node_id: uuid.UUID, claim_ttl_seconds: int = 600
    ) -> SwarmTaskSchema | None:
        """Atomically claim a ``ready`` task. Returns the task if the claim won, else None.

        Atomicity comes from the conditional UPDATE (``WHERE status='ready'``) plus
        SQLite WAL + busy_timeout — only one worker can flip a task out of ``ready``.
        """
        expires = datetime.now(UTC) + timedelta(seconds=claim_ttl_seconds)
        async with self._session() as sess:
            res = await sess.execute(
                update(SwarmTask)
                .where(SwarmTask.id == task_id, SwarmTask.status == "ready")
                .values(
                    status="claimed",
                    assignee_node_id=node_id,
                    claim_expires_at=expires,
                )
            )
            cursor = cast(CursorResult[Any], res)
            if cursor.rowcount == 0:
                return None
            got = await sess.execute(select(SwarmTask).where(SwarmTask.id == task_id))
            item = got.scalar_one_or_none()
            return SwarmTaskSchema.model_validate(item) if item else None

    async def release_task(self, task_id: uuid.UUID) -> None:
        async with self._session() as sess:
            await sess.execute(
                update(SwarmTask)
                .where(SwarmTask.id == task_id)
                .values(status="ready", assignee_node_id=None, claim_expires_at=None)
            )

    # ── Handoffs ────────────────────────────────────────────────────────────
    async def create_handoff(self, **kwargs: Any) -> HandoffSchema:
        async with self._session() as sess:
            item = Handoff(**kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return HandoffSchema.model_validate(item)

    async def list_handoffs(self, swarm_id: uuid.UUID) -> list[HandoffSchema]:
        async with self._session() as sess:
            res = await sess.execute(
                select(Handoff).where(Handoff.swarm_id == swarm_id).order_by(Handoff.created_at)
            )
            return [HandoffSchema.model_validate(i) for i in res.scalars().all()]

    # ── Manifests (approval gate) ───────────────────────────────────────────
    async def create_manifest(self, **kwargs: Any) -> SwarmManifestSchema:
        async with self._session() as sess:
            item = SwarmManifest(**kwargs)
            sess.add(item)
            await sess.flush()
            await sess.refresh(item)
            return SwarmManifestSchema.model_validate(item)

    async def get_manifest_for_swarm(self, swarm_id: uuid.UUID) -> SwarmManifestSchema | None:
        async with self._session() as sess:
            res = await sess.execute(
                select(SwarmManifest)
                .where(SwarmManifest.swarm_id == swarm_id)
                .order_by(SwarmManifest.created_at.desc())
            )
            item = res.scalars().first()
            return SwarmManifestSchema.model_validate(item) if item else None

    async def update_manifest(
        self, manifest_id: uuid.UUID, **kwargs: Any
    ) -> SwarmManifestSchema | None:
        async with self._session() as sess:
            await sess.execute(
                update(SwarmManifest).where(SwarmManifest.id == manifest_id).values(**kwargs)
            )
            res = await sess.execute(select(SwarmManifest).where(SwarmManifest.id == manifest_id))
            item = res.scalar_one_or_none()
            return SwarmManifestSchema.model_validate(item) if item else None
