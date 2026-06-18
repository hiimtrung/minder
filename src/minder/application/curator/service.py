from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional, List

from minder.config import MinderConfig
from minder.domain.entities.skill import SkillSchema
from minder.graph.state import GraphState
from minder.learning.pattern_extractor import PatternExtractor
from minder.learning.skill_synthesizer import SkillSynthesizer
from minder.learning.quality_optimizer import QualityOptimizer
from minder.llm.factory import create_llm
from minder.store.interfaces import IOperationalStore

logger = logging.getLogger(__name__)

# Registry for in-memory recent GraphStates to curate
_RECENT_GRAPH_STATES: dict[uuid.UUID, GraphState] = {}


def register_session_state(session_id: uuid.UUID, state: GraphState) -> None:
    _RECENT_GRAPH_STATES[session_id] = state
    if len(_RECENT_GRAPH_STATES) > 100:
        first_key = next(iter(_RECENT_GRAPH_STATES))
        _RECENT_GRAPH_STATES.pop(first_key, None)


class SkillCurator:
    def __init__(self, store: IOperationalStore, config: MinderConfig, embedder: Any = None) -> None:
        self._store = store
        self._config = config
        
        if embedder is None:
            from minder.embedding.local import LocalEmbeddingProvider
            embedder = LocalEmbeddingProvider(
                llama_cpp_model_repo=config.embedding.llama_cpp_model_repo,
                llama_cpp_model_file=config.embedding.llama_cpp_model_file,
                dimensions=config.embedding.dimensions,
                runtime=config.embedding.runtime,
            )
        self._embedder = embedder
        self._pattern_extractor = PatternExtractor()
        self._skill_synthesizer = SkillSynthesizer(store, embedder)
        self._quality_optimizer = QualityOptimizer(store, embedder)
        try:
            self._llm = create_llm(config.llm)
        except Exception as e:
            logger.warning("Failed to create LLM for SkillCurator: %s", e)
            self._llm = None

    async def curate_after_session(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        """Analyze a session, extract pattern, synthesize skill and generate proposal review card."""
        state = _RECENT_GRAPH_STATES.get(session_id)
        if state is None:
            logger.debug("No in-memory GraphState found for session %s", session_id)
            return None

        pattern = self._pattern_extractor.extract(state)
        if pattern is None:
            logger.debug("No pattern extracted for session %s (quality too low or not complete)", session_id)
            return None

        scores = {"reuse_potential": 0.5, "novelty": 0.5, "risk": 0.1}
        recommendation = "approve"
        reason = "Automatically synthesized from successful session execution."
        
        near_duplicates = []
        try:
            title = f"Workflow pattern: {pattern['query'][:80]}"
            content = f"Query: {pattern['query']}\nWorkflow: {pattern.get('workflow_name')}"
            temp_emb = self._embedder.embed(f"{title}\n{content}")
            for skill in await self._store.list_skills_by_kind(is_memory=False):
                tags = list(getattr(skill, "tags", []) or [])
                if getattr(skill, "deprecated", False):
                    continue
                existing_emb = skill.embedding if isinstance(skill.embedding, list) else None
                if existing_emb:
                    from minder.learning.skill_synthesizer import _cosine
                    sim = _cosine(temp_emb, existing_emb)
                    if sim >= 0.70:
                        near_duplicates.append(str(skill.title))
        except Exception as e:
            logger.warning("Error finding near duplicates: %s", e)

        if self._llm:
            try:
                prompt = (
                    "You are the Minder Skill Curator. Analyze this workflow pattern:\n"
                    f"Query: {pattern['query']}\n"
                    f"Workflow: {pattern['workflow_name']} step: {pattern['current_step']}\n"
                    f"Quality: {pattern['quality_score']}\n"
                    f"Sources used: {', '.join(pattern['sources_used'])}\n\n"
                    "Evaluate this pattern and generate a JSON review card. Return ONLY a valid JSON object in this format:\n"
                    "{\n"
                    "  \"reuse_potential\": 0.8,\n"
                    "  \"novelty\": 0.7,\n"
                    "  \"risk\": 0.1,\n"
                    "  \"recommendation\": \"approve\",\n"
                    "  \"reason\": \"clean reason here\"\n"
                    "}"
                )
                
                llm_state = GraphState(
                    query=prompt,
                    session_id=None,
                    reasoning_output={"prompt": prompt},
                    workflow_context={"guidance": "Return ONLY the JSON block, no markdown, no explanation."}
                )
                
                res = self._llm.generate(llm_state)
                res_text = str(res.get("text", "")).strip()
                if res_text.startswith("```"):
                    parts = res_text.split("```")
                    if len(parts) >= 2:
                        res_text = parts[1].strip()
                        if res_text.startswith("json"):
                            res_text = res_text[4:].strip()
                
                card = json.loads(res_text)
                scores["reuse_potential"] = float(card.get("reuse_potential", 0.5))
                scores["novelty"] = float(card.get("novelty", 0.5))
                scores["risk"] = float(card.get("risk", 0.1))
                recommendation = str(card.get("recommendation", "approve"))
                reason = str(card.get("reason", reason))
            except Exception as e:
                logger.debug("LLM review proposal generation failed (using defaults): %s", e)

        proposal = {
            "title": f"Workflow pattern: {pattern['query'][:80]}",
            "proposed_content": (
                f"## Workflow Execution Pattern\n\n"
                f"**Query**: {pattern['query']}\n\n"
                f"**Workflow**: {pattern['workflow_name']} / step: {pattern['current_step']}\n\n"
                f"**Outcome**: {pattern['edge']} (quality: {pattern['quality_score']:.2f})\n\n"
                f"**Sources used**: {', '.join(pattern['sources_used']) or 'none'}\n"
            ),
            "source_pattern": f"session:{session_id}",
            "evidence": [str(session_id)],
            "scores": scores,
            "near_duplicates": near_duplicates,
            "recommendation": f"{recommendation}: {reason}",
        }

        res = await self._skill_synthesizer.synthesize(
            pattern,
            status="pending_review",
            review_proposal=proposal,
        )
        if res:
            await self._quality_optimizer.optimize(state)
            return {"skill_id": res["id"], "proposal": proposal}
        return None

    async def reap(self) -> dict[str, Any]:
        """Scan active or pending auto_synthesized skills to prune those with low quality/utility."""
        skills = await self._store.list_skills_by_kind(is_memory=False)
        reaped_count = 0
        archived_skills = []

        for skill in skills:
            tags = list(getattr(skill, "tags", []) or [])
            if "auto_synthesized" not in tags:
                continue

            if skill.status == "pending_review":
                from datetime import datetime, UTC
                created_at = skill.created_at
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        created_at = datetime.now(UTC)
                
                # Check if it has been expired for 7 days
                delta = datetime.now(UTC) - created_at
                if delta.days >= 7:
                    await self._store.update_skill(skill.id, status="archived", deprecated=True)
                    reaped_count += 1
                    archived_skills.append(str(skill.title))
            elif skill.status == "active" and skill.quality_score < 0.3 and skill.usage_count > 5:
                await self._store.update_skill(skill.id, status="archived", deprecated=True)
                reaped_count += 1
                archived_skills.append(str(skill.title))

        return {"reaped_count": reaped_count, "archived": archived_skills}
