from __future__ import annotations

import asyncio
from datetime import datetime, UTC
import logging
from pathlib import Path
import uuid
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]

from minder.config import MinderConfig
from minder.store.interfaces import IOperationalStore
from minder.domain.entities.maintenance import MaintenanceJobSchema

logger = logging.getLogger(__name__)

# Global registry for active scheduler instance to receive touch hooks from middlewares/transports
_SCHEDULER_INSTANCE: MaintenanceScheduler | None = None


def get_scheduler() -> MaintenanceScheduler | None:
    return _SCHEDULER_INSTANCE


def touch_activity() -> None:
    if _SCHEDULER_INSTANCE is not None:
        _SCHEDULER_INSTANCE.touch_activity()


def register_active_session(session_id: uuid.UUID) -> None:
    if _SCHEDULER_INSTANCE is not None:
        _SCHEDULER_INSTANCE.register_active_session(session_id)


def unregister_active_session(session_id: uuid.UUID) -> None:
    if _SCHEDULER_INSTANCE is not None:
        _SCHEDULER_INSTANCE.unregister_active_session(session_id)


class MaintenanceScheduler:
    def __init__(
        self,
        store: IOperationalStore,
        config: MinderConfig,
        vector_store: Any = None,
        memory_service: Any = None,
        curator: Any = None,
        error_learner: Any = None,
    ) -> None:
        self._store = store
        self._config = config
        self._vector_store = vector_store
        self._memory_service = memory_service
        self._curator = curator
        self._error_learner = error_learner

        global _SCHEDULER_INSTANCE
        _SCHEDULER_INSTANCE = self

        # State tracking
        self._last_activity_time: datetime = datetime.now(UTC)
        self._active_sessions: set[uuid.UUID] = set()
        self._running_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    def touch_activity(self) -> None:
        """HTTP/MCP activity hook to refresh last activity timer."""
        self._last_activity_time = datetime.now(UTC)

    def register_active_session(self, session_id: uuid.UUID) -> None:
        """Query starts execution hook."""
        self._active_sessions.add(session_id)

    def unregister_active_session(self, session_id: uuid.UUID) -> None:
        """Query finishes execution hook."""
        self._active_sessions.discard(session_id)

    @property
    def is_idle(self) -> bool:
        """Idle detection checks. True if no active sessions and idle threshold reached."""
        if self._active_sessions:
            return False
        idle_s = (datetime.now(UTC) - self._last_activity_time).total_seconds()
        return idle_s >= self._config.maintenance.idle_threshold_seconds

    @property
    def current_mode(self) -> str:
        """Current execution mode (active/report). Auto-promotes if idle continuously >= 3 hours."""
        configured_mode = self._config.maintenance.mode
        if configured_mode == "active":
            return "active"

        # Check for 3-hour idle trigger
        auto_active_hours = self._config.maintenance.auto_active_after_idle_hours
        if auto_active_hours > 0:
            idle_s = (datetime.now(UTC) - self._last_activity_time).total_seconds()
            if idle_s >= auto_active_hours * 3600.0:
                return "active"

        return "report"

    def start(self) -> None:
        """Start background scheduler loop."""
        if self._running_task is None or self._running_task.done():
            self._shutdown_event.clear()
            self._running_task = asyncio.create_task(self._loop())
            logger.info("MaintenanceScheduler background loop started.")

    async def stop(self) -> None:
        """Stop background scheduler loop."""
        self._shutdown_event.set()
        if self._running_task:
            self._running_task.cancel()
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass
            self._running_task = None
            logger.info("MaintenanceScheduler background loop stopped.")

    async def _loop(self) -> None:
        await self._init_jobs_in_db()
        while not self._shutdown_event.is_set():
            try:
                tick_s = self._config.maintenance.tick_seconds
                await asyncio.sleep(tick_s)
                
                if not self._config.maintenance.enabled:
                    continue
                
                await self._run_due_jobs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in MaintenanceScheduler loop: %s", e, exc_info=True)

    async def _init_jobs_in_db(self) -> None:
        try:
            db_jobs = {job.name: job for job in await self._store.list_maintenance_jobs()}
            for job_cfg in self._config.maintenance.jobs:
                if job_cfg.name not in db_jobs:
                    await self._store.create_maintenance_job(
                        name=job_cfg.name,
                        schedule=job_cfg.schedule,
                        enabled=True,
                        require_idle=job_cfg.require_idle,
                        max_runtime_s=job_cfg.max_runtime_s,
                    )
                else:
                    db_job = db_jobs[job_cfg.name]
                    if db_job.schedule != job_cfg.schedule or db_job.max_runtime_s != job_cfg.max_runtime_s:
                        await self._store.update_maintenance_job(
                            db_job.id,
                            schedule=job_cfg.schedule,
                            max_runtime_s=job_cfg.max_runtime_s,
                        )
        except Exception as e:
            logger.error("Failed to initialize maintenance jobs in database: %s", e)

    async def _run_due_jobs(self) -> None:
        jobs = await self._store.list_maintenance_jobs()
        for job in jobs:
            if not job.enabled:
                continue

            if job.require_idle and not self.is_idle:
                continue

            if self._is_due(job.schedule, job.last_run_at):
                await self.run_job(job)

    def _is_due(self, schedule: str, last_run_at: datetime | None) -> bool:
        if not last_run_at:
            return True
        now = datetime.now(UTC)
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=UTC)
        try:
            cron = croniter(schedule, last_run_at)
            next_run = cron.get_next(datetime)
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=UTC)
            return next_run <= now
        except Exception as e:
            logger.warning("Invalid cron expression '%s': %s", schedule, e)
            return False

    async def run_job(self, job: MaintenanceJobSchema) -> None:
        logger.info("Starting maintenance job: %s (mode: %s)", job.name, self.current_mode)
        
        run_id = uuid.uuid4()
        started_at = datetime.now(UTC)
        mode = self.current_mode
        
        await self._store.create_maintenance_run(
            id=run_id,
            job_name=job.name,
            started_at=started_at,
            status="running",
            mode=mode,
        )
        
        await self._store.update_maintenance_job(
            job.id,
            last_run_at=started_at,
            last_status="running",
        )
        
        summary = ""
        error_msg = ""
        status = "success"
        
        try:
            summary = await asyncio.wait_for(
                self._execute_job_logic(job.name, mode),
                timeout=float(job.max_runtime_s)
            )
        except asyncio.TimeoutError:
            status = "failed"
            error_msg = f"Job timeout after {job.max_runtime_s} seconds"
            logger.warning("Maintenance job %s timed out", job.name)
        except Exception as e:
            status = "failed"
            error_msg = str(e)
            logger.error("Maintenance job %s failed: %s", job.name, e, exc_info=True)
            
        finished_at = datetime.now(UTC)
        duration_s = (finished_at - started_at).total_seconds()
        
        await self._store.update_maintenance_run(
            run_id,
            finished_at=finished_at,
            status=status,
            duration_s=duration_s,
            summary=summary if status == "success" else None,
            error_message=error_msg if status == "failed" else None,
        )
        
        await self._store.update_maintenance_job(
            job.id,
            last_status=status,
            last_summary=summary if status == "success" else error_msg,
        )

    async def _execute_job_logic(self, name: str, mode: str) -> str:
        dry_run = (mode == "report")
        
        if name == "sqlite_vacuum":
            if not dry_run:
                db_path = self._config.relational_store.db_path
                self._backup_file(db_path)
                await self._store.vacuum()
                return "Successfully vacuumed relational store database."
            return "Dry run: SQLite vacuum would be executed."
            
        elif name == "vector_optimize":
            if self._vector_store:
                if not dry_run:
                    vector_path = self._config.turbovec.db_path
                    self._backup_file(vector_path)
                    await self._vector_store.optimize()
                    return "Successfully optimized vector database index."
                return "Dry run: Vector database optimization would be executed."
            return "Vector store is not configured."
            
        elif name == "memory_dedupe":
            if self._memory_service:
                memories = await self._store.list_skills_by_kind(is_memory=True)
                memory_ids = [str(m.id) for m in memories]
                if len(memory_ids) < 2:
                    return "No duplicate memories to compact (less than 2 memories total)."
                res = await self._memory_service.minder_memory_compact(
                    memory_ids=memory_ids,
                    similarity_threshold=0.92,
                    dry_run=dry_run,
                )
                if dry_run:
                    return f"Dry run: Found {res.get('duplicate_group_count', 0)} duplicate groups containing {res.get('candidate_count', 0)} candidates."
                return f"Successfully compacted {res.get('compacted_count', 0)} memories, deleted {res.get('deleted_count', 0)} duplicates."
            return "Memory service is not configured."
            
        elif name == "chat_history_compact":
            sessions = await self._store.list_sessions()
            from minder.application.context_compactor import HistoryCompactor
            compactor = HistoryCompactor(keep_recent=8, history_budget_ratio=0.4)
            compacted_sessions = 0
            
            for session in sessions:
                history_docs = await self._store.list_history_for_session(session.id)
                if len(history_docs) > 15:
                    ordered_docs = sorted(
                        history_docs,
                        key=lambda doc: (
                            doc.created_at.isoformat() if hasattr(doc.created_at, "isoformat") else "",
                            str(doc.id)
                        )
                    )
                    history_list = [
                        {
                            "role": str(getattr(doc, "role", "")),
                            "content": str(getattr(doc, "content", "")),
                            "reasoning_trace": str(getattr(doc, "reasoning_trace", "")),
                            "tool_calls": getattr(doc, "tool_calls", None),
                            "latency_ms": getattr(doc, "latency_ms", 0),
                        }
                        for doc in ordered_docs
                    ]
                    compacted_list = compactor.compact(history_list, context_length=2048)
                    if len(compacted_list) < len(history_list):
                        compacted_sessions += 1
                        if not dry_run:
                            await self._store.delete_history_for_session(session.id)
                            for item in compacted_list:
                                await self._store.create_history(
                                    session_id=session.id,
                                    role=item["role"],
                                    content=item["content"],
                                    reasoning_trace=item.get("reasoning_trace", ""),
                                    tool_calls=item.get("tool_calls"),
                                    latency_ms=item.get("latency_ms", 0),
                                )
            if dry_run:
                return f"Dry run: Would compact {compacted_sessions} session chat histories."
            return f"Successfully compacted {compacted_sessions} session chat histories."
            
        elif name == "graph_prune":
            repos = await self._store.list_repositories()
            repos_by_id = {str(repo.id): repo for repo in repos}
            pruned_count = 0
            
            graph_store: Any = getattr(self._store, "_graph_store", None)
            if not graph_store:
                if hasattr(self._store, "list_nodes") and hasattr(self._store, "delete_node"):
                    graph_store = self._store

            if graph_store:
                try:
                    nodes = await graph_store.list_nodes()
                    for node in nodes:
                        if node.node_type == "file" and node.repo_id in repos_by_id:
                            repo = repos_by_id[node.repo_id]
                            state_path = str(getattr(repo, "state_path", "") or "")
                            if state_path:
                                state_root = Path(state_path).expanduser()
                                root_path = state_root.parent if state_root.name == ".minder" else state_root
                                file_path = root_path / node.name
                                if not file_path.exists():
                                    pruned_count += 1
                                    if not dry_run:
                                        await graph_store.delete_node(node.id)
                except Exception as e:
                    logger.warning("Error pruning graph file nodes: %s", e)
            
            untracked_deleted = 0
            for repo in repos:
                try:
                    tracked = set(getattr(repo, "tracked_branches", []) or [])
                    if tracked and graph_store and hasattr(graph_store, "list_repo_branches") and hasattr(graph_store, "delete_nodes_by_scope"):
                        branches = await graph_store.list_repo_branches(str(repo.id))
                        for b in branches:
                            if b not in tracked:
                                untracked_deleted += 1
                                if not dry_run:
                                    await graph_store.delete_nodes_by_scope(repo_id=str(repo.id), branch=b)
                except Exception as e:
                    logger.warning("Error pruning branch %s: %s", repo.id, e)
                    
            if dry_run:
                return f"Dry run: Would prune {pruned_count} missing file nodes and {untracked_deleted} stale branch scopes."
            return f"Successfully pruned {pruned_count} missing file nodes and {untracked_deleted} stale branch scopes."
            
        elif name == "skill_curate":
            if self._curator:
                res = await self._curator.reap()
                reaped_count = res.get("reaped_count", 0)
                archived = ", ".join(res.get("archived", []))
                if dry_run:
                    return f"Dry run: Skill curator would reap {reaped_count} skills."
                return f"Successfully reaped {reaped_count} obsolete auto-synthesized skills: {archived or 'none'}."
            return "Curator service is not configured."
            
        elif name == "error_rules_refresh":
            if self._error_learner:
                unresolved = [err for err in await self._store.list_errors() if not err.resolved]
                extracted_count = 0
                for err in unresolved:
                    ctx = getattr(err, "context", None) or {}
                    query = ctx.get("query")
                    if query:
                        failures = []
                        transition_log = ctx.get("transition_log", [])
                        for idx, step in enumerate(transition_log):
                            edge = step.get("edge")
                            if edge in {"verification_failed", "guard_failed"}:
                                failures.append({
                                    "attempt": step.get("attempt", idx + 1),
                                    "edge": edge,
                                    "reason": err.error_message,
                                    "provider": step.get("provider", "unknown")
                                })
                        if not failures:
                            failures.append({
                                "attempt": 1,
                                "edge": "pipeline_failed",
                                "reason": err.error_message,
                                "provider": ctx.get("provider", "unknown")
                            })
                        
                        from minder.graph.state import GraphState
                        state = GraphState(
                            query=query,
                            session_id=None,
                            metadata={"attempt_failures": failures}
                        )
                        rule = await self._error_learner.learn(state)
                        if rule:
                            extracted_count += 1
                            if not dry_run:
                                await self._store.update_error(err.id, resolved=True)
                if dry_run:
                    return f"Dry run: Error learner would extract rules from {len(unresolved)} failed executions."
                return f"Successfully extracted rules for {extracted_count} failed executions."
            return "Error learner service is not configured."
            
        return f"Unknown job logic for: {name}"

    def _backup_file(self, file_path_str: str) -> None:
        try:
            import shutil
            from pathlib import Path
            src = Path(file_path_str).expanduser()
            if src.exists():
                dest = src.with_suffix(src.suffix + ".bak")
                shutil.copy2(src, dest)
                logger.info("Created backup: %s -> %s", src, dest)
        except Exception as e:
            logger.error("Failed to create backup of %s: %s", file_path_str, e)
