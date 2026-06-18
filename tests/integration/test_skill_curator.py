from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from minder.application.curator.service import SkillCurator, register_session_state
from minder.graph.state import GraphState
from minder.config import MinderConfig


@pytest.mark.asyncio
async def test_curate_after_session_success() -> None:
    session_id = uuid.uuid4()
    
    # Create a dummy GraphState to associate with the session
    state = GraphState(
        query="Implement db index",
        session_id=session_id,
        evaluation={"quality_score": 0.8},
        guard_result={"passed": True},
        verification_result={"passed": True},
        llm_output={"text": "CREATE INDEX idx_name ON table_name(column)", "provider": "mock"},
        reasoning_output={"sources": [{"path": "schema.sql", "title": "schema"}]},
        workflow_context={"workflow_name": "db-setup", "current_step": "Index Creation"},
        metadata={"edge": "complete"},
    )
    register_session_state(session_id, state)

    # Mock store and embedding provider
    store = AsyncMock()
    store.list_skills_by_kind = AsyncMock(return_value=[])
    
    mock_skill_result = {"id": str(uuid.uuid4()), "title": "Synthesized Skill"}
    
    config = MinderConfig()
    config.llm.provider = "mock"
    config.llm.runtime = "mock"
    
    embedder = MagicMock()
    embedder.embed = MagicMock(return_value=[0.1] * 16)
    
    curator = SkillCurator(store, config, embedder=embedder)
    
    # Mock synthesiser and quality optimizer
    curator._skill_synthesizer = AsyncMock()
    curator._skill_synthesizer.synthesize = AsyncMock(return_value=mock_skill_result)
    curator._quality_optimizer = AsyncMock()
    curator._quality_optimizer.optimize = AsyncMock()
    
    res = await curator.curate_after_session(session_id)
    
    assert res is not None
    assert res["skill_id"] == mock_skill_result["id"]
    curator._skill_synthesizer.synthesize.assert_awaited_once()
    curator._quality_optimizer.optimize.assert_awaited_once()


@pytest.mark.asyncio
async def test_curator_reaps_expired_pending_skills() -> None:
    from datetime import datetime, UTC, timedelta
    
    store = AsyncMock()
    
    class FakeSkill:
        def __init__(self, title: str, status: str, created_at: datetime, quality_score: float, usage_count: int) -> None:
            self.id = uuid.uuid4()
            self.title = title
            self.status = status
            self.created_at = created_at
            self.quality_score = quality_score
            self.usage_count = usage_count
            self.tags = ["auto_synthesized"]

    # 1 expired pending skill (8 days old)
    expired_pending = FakeSkill("Expired pending", "pending_review", datetime.now(UTC) - timedelta(days=8), 0.8, 0)
    # 1 recent pending skill (2 days old) - should NOT be reaped
    recent_pending = FakeSkill("Recent pending", "pending_review", datetime.now(UTC) - timedelta(days=2), 0.8, 0)
    # 1 low quality active skill (quality 0.2, high usage) - should be reaped
    low_quality_active = FakeSkill("Low quality active", "active", datetime.now(UTC) - timedelta(days=5), 0.2, 10)
    
    store.list_skills_by_kind = AsyncMock(return_value=[expired_pending, recent_pending, low_quality_active])
    store.update_skill = AsyncMock(return_value=None)
    
    config = MinderConfig()
    curator = SkillCurator(store, config)
    
    reap_res = await curator.reap()
    
    assert reap_res["reaped_count"] == 2
    assert "Expired pending" in reap_res["archived"]
    assert "Low quality active" in reap_res["archived"]
    assert "Recent pending" not in reap_res["archived"]
