from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from minder.config import MinderConfig
from minder.store.interfaces import IOperationalStore
from minder.tools.skills import SkillTools


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AdminJobService:
    _MAX_EVENT_HISTORY = 100

    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._store = store
        self._config = config
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[
            int, tuple[asyncio.Queue[dict[str, Any]], Callable[[dict[str, Any]], bool]]
        ] = {}
        self._subscriber_id = 0
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        *,
        job_type: str,
        title: str,
        requested_by_user_id: uuid.UUID | None,
        payload: dict[str, Any],
    ) -> Any:
        job = await self._store.create_admin_job(
            id=uuid.uuid4(),
            job_type=job_type,
            title=title,
            status="queued",
            requested_by_user_id=requested_by_user_id,
            payload=payload,
            result_payload=None,
            error_message=None,
            progress_current=0,
            progress_total=0,
            message="Queued",
            events=[
                self._event_payload(
                    event_type="queued", status="queued", message="Job queued"
                )
            ],
            created_at=_utcnow(),
            updated_at=_utcnow(),
            started_at=None,
            finished_at=None,
        )
        await self._publish(self._snapshot(job))
        self._ensure_running(job)
        return job

    def subscribe(
        self,
        *,
        job_id: str | None = None,
        job_type: str | None = None,
        statuses: set[str] | None = None,
    ) -> tuple[asyncio.Queue[dict[str, Any]], Callable[[], None]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def _matches(payload: dict[str, Any]) -> bool:
            if job_id and str(payload.get("id")) != job_id:
                return False
            if job_type and str(payload.get("job_type")) != job_type:
                return False
            if statuses and str(payload.get("status")) not in statuses:
                return False
            return True

        subscriber_key = self._subscriber_id
        self._subscriber_id += 1
        self._subscribers[subscriber_key] = (queue, _matches)

        def unsubscribe() -> None:
            self._subscribers.pop(subscriber_key, None)

        return queue, unsubscribe

    async def publish_existing(self, job: Any) -> None:
        await self._publish(self._snapshot(job))

    def _ensure_running(self, job: Any) -> None:
        job_id = str(job.id)
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return
        self._tasks[job_id] = asyncio.create_task(self._run(job_id))

    async def _run(self, job_id: str) -> None:
        try:
            job = await self._store.get_admin_job_by_id(uuid.UUID(job_id))
            if job is None:
                return
            await self._update_job(
                job_id,
                status="running",
                message="Starting job",
                started_at=_utcnow(),
                error_message=None,
                events=self._append_event_list(
                    list(getattr(job, "events", []) or []),
                    self._event_payload(
                        event_type="started",
                        status="running",
                        message="Job started",
                    ),
                ),
            )
            if str(getattr(job, "job_type", "")) == "skill_import_git":
                await self._run_skill_import(job_id)
                return
            raise ValueError(
                f"Unsupported admin job type: {getattr(job, 'job_type', None)}"
            )
        except Exception as exc:
            await self._fail_job(job_id, str(exc))
        finally:
            self._tasks.pop(job_id, None)

    async def _run_skill_import(self, job_id: str) -> None:
        job = await self._store.get_admin_job_by_id(uuid.UUID(job_id))
        if job is None:
            return
        payload = dict(getattr(job, "payload", {}) or {})
        tools = SkillTools(self._store, self._config)

        async def emit_progress(update: dict[str, Any]) -> None:
            current_job = await self._store.get_admin_job_by_id(uuid.UUID(job_id))
            if current_job is None:
                return
            message = str(
                update.get("message") or getattr(current_job, "message", "Running")
            )
            progress_current = int(
                update.get(
                    "progress_current", getattr(current_job, "progress_current", 0)
                )
                or 0
            )
            progress_total = int(
                update.get("progress_total", getattr(current_job, "progress_total", 0))
                or 0
            )
            details = (
                update.get("details")
                if isinstance(update.get("details"), dict)
                else None
            )
            next_events = self._append_event_list(
                list(getattr(current_job, "events", []) or []),
                self._event_payload(
                    event_type=str(update.get("event_type") or "progress"),
                    status="running",
                    message=message,
                    progress_current=progress_current,
                    progress_total=progress_total,
                    details=details,
                ),
            )
            await self._update_job(
                job_id,
                status="running",
                message=message,
                progress_current=progress_current,
                progress_total=progress_total,
                events=next_events,
            )

        result = await tools.minder_skill_import_git(
            repo_url=str(payload.get("repo_url") or ""),
            source_path=str(payload.get("path") or "skills"),
            ref=str(payload.get("ref")) if payload.get("ref") else None,
            provider=str(payload.get("provider")) if payload.get("provider") else None,
            excerpt_kind=str(payload.get("excerpt_kind") or "none"),
            progress_callback=emit_progress,
        )
        completed_job = await self._store.get_admin_job_by_id(uuid.UUID(job_id))
        completed_events = self._append_event_list(
            list(getattr(completed_job, "events", []) or []),
            self._event_payload(
                event_type="completed",
                status="completed",
                message="Job completed",
                progress_current=int(result.get("imported_count", 0) or 0),
                progress_total=int(result.get("imported_count", 0) or 0),
                details={"imported_count": result.get("imported_count", 0)},
            ),
        )
        await self._update_job(
            job_id,
            status="completed",
            message="Skill import completed",
            progress_current=int(result.get("imported_count", 0) or 0),
            progress_total=int(result.get("imported_count", 0) or 0),
            result_payload=result,
            error_message=None,
            finished_at=_utcnow(),
            events=completed_events,
        )

    async def _fail_job(self, job_id: str, error_message: str) -> None:
        job = await self._store.get_admin_job_by_id(uuid.UUID(job_id))
        existing_events = (
            list(getattr(job, "events", []) or []) if job is not None else []
        )
        await self._update_job(
            job_id,
            status="failed",
            message=error_message,
            error_message=error_message,
            finished_at=_utcnow(),
            events=self._append_event_list(
                existing_events,
                self._event_payload(
                    event_type="failed",
                    status="failed",
                    message=error_message,
                ),
            ),
        )

    async def _update_job(self, job_id: str, **kwargs: Any) -> Any:
        kwargs["updated_at"] = _utcnow()
        updated = await self._store.update_admin_job(uuid.UUID(job_id), **kwargs)
        if updated is not None:
            await self._publish(self._snapshot(updated))
        return updated

    async def _publish(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.values())
        for queue, matcher in subscribers:
            if matcher(payload):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(payload)

    @classmethod
    def _event_payload(
        cls,
        *,
        event_type: str,
        status: str,
        message: str,
        progress_current: int | None = None,
        progress_total: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "status": status,
            "message": message,
            "progress_current": progress_current,
            "progress_total": progress_total,
            "details": details or {},
            "created_at": _utcnow().isoformat(),
        }

    @classmethod
    def _append_event_list(
        cls,
        existing: list[dict[str, Any]],
        event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        combined = [*existing, event]
        if len(combined) <= cls._MAX_EVENT_HISTORY:
            return combined
        return combined[-cls._MAX_EVENT_HISTORY :]

    @staticmethod
    def _snapshot(job: Any) -> dict[str, Any]:
        created_at = getattr(job, "created_at", None)
        updated_at = getattr(job, "updated_at", None)
        started_at = getattr(job, "started_at", None)
        finished_at = getattr(job, "finished_at", None)
        return {
            "id": str(job.id),
            "job_type": str(getattr(job, "job_type", "")),
            "title": str(getattr(job, "title", "")),
            "status": str(getattr(job, "status", "queued")),
            "requested_by_user_id": (
                str(getattr(job, "requested_by_user_id", ""))
                if getattr(job, "requested_by_user_id", None)
                else None
            ),
            "payload": dict(getattr(job, "payload", {}) or {}),
            "result_payload": getattr(job, "result_payload", None),
            "error_message": getattr(job, "error_message", None),
            "progress_current": int(getattr(job, "progress_current", 0) or 0),
            "progress_total": int(getattr(job, "progress_total", 0) or 0),
            "message": getattr(job, "message", None),
            "events": list(getattr(job, "events", []) or []),
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "started_at": started_at.isoformat() if started_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
        }


async def iter_job_stream(
    *,
    queue: asyncio.Queue[dict[str, Any]],
    request_is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[dict[str, Any]]:
    while True:
        if await request_is_disconnected():
            return
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=15)
        except TimeoutError:
            yield {"type": "keepalive"}
            continue
        yield {"type": "job", "payload": payload}
