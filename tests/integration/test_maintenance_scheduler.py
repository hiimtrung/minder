from __future__ import annotations

import uuid
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from minder.application.maintenance.scheduler import MaintenanceScheduler
from minder.config import MinderConfig
from minder.domain.entities.maintenance import MaintenanceJobSchema


@pytest.mark.asyncio
async def test_scheduler_idle_detection() -> None:
    config = MinderConfig()
    config.maintenance.idle_threshold_seconds = 2
    
    store = AsyncMock()
    scheduler = MaintenanceScheduler(store, config)
    
    # Initially not idle
    assert not scheduler.is_idle
    
    # Force last activity time to be older
    scheduler._last_activity_time = datetime.now(UTC) - timedelta(seconds=3)
    assert scheduler.is_idle
    
    # Active session prevents idle state even if activity threshold is met
    session_id = uuid.uuid4()
    scheduler.register_active_session(session_id)
    assert not scheduler.is_idle
    
    # Unregister makes it idle again
    scheduler.unregister_active_session(session_id)
    assert scheduler.is_idle


@pytest.mark.asyncio
async def test_scheduler_mode_promotion() -> None:
    config = MinderConfig()
    config.maintenance.mode = "report"
    config.maintenance.auto_active_after_idle_hours = 0.001  # very short (3.6 seconds)
    
    store = AsyncMock()
    scheduler = MaintenanceScheduler(store, config)
    
    assert scheduler.current_mode == "report"
    
    # Inactivity exceeds threshold
    scheduler._last_activity_time = datetime.now(UTC) - timedelta(seconds=5)
    assert scheduler.current_mode == "active"


@pytest.mark.asyncio
async def test_scheduler_executes_due_jobs() -> None:
    config = MinderConfig()
    config.maintenance.enabled = True
    config.maintenance.mode = "active"
    
    job_cfg = MagicMock()
    job_cfg.name = "sqlite_vacuum"
    job_cfg.schedule = "*/5 * * * *"
    job_cfg.require_idle = False
    job_cfg.max_runtime_s = 60
    config.maintenance.jobs = [job_cfg]
    
    store = AsyncMock()
    
    # Mock return values for listed jobs
    mock_job = MaintenanceJobSchema(
        id=uuid.uuid4(),
        name="sqlite_vacuum",
        schedule="*/5 * * * *",
        enabled=True,
        require_idle=False,
        max_runtime_s=60,
        last_run_at=None,
        last_status=None,
        last_summary=None,
    )
    store.list_maintenance_jobs = AsyncMock(return_value=[mock_job])
    store.create_maintenance_run = AsyncMock()
    store.update_maintenance_run = AsyncMock()
    store.update_maintenance_job = AsyncMock()
    store.vacuum = AsyncMock()
    
    scheduler = MaintenanceScheduler(store, config)
    
    # Manually trigger due checks and execution
    await scheduler._run_due_jobs()
    
    store.create_maintenance_run.assert_awaited_once()
    store.vacuum.assert_awaited_once()
    store.update_maintenance_run.assert_awaited_once()
