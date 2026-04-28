"""P7-T05 — Post-execution reflection node: orchestrates the learning subsystem."""

from __future__ import annotations

import logging
from typing import Any

from minder.graph.state import GraphState
from minder.learning.error_learner import ErrorLearner
from minder.learning.pattern_extractor import extract_pattern
from minder.learning.quality_optimizer import QualityOptimizer
from minder.learning.skill_synthesizer import SkillSynthesizer
from minder.store.interfaces import IOperationalStore

logger = logging.getLogger(__name__)

_FAILURE_EDGES = {"guard_failed", "verification_failed"}


class ReflectionNode:
    """Async post-execution node that drives workflow learning.

    On every completed run it:
    - Extracts the workflow pattern (success path)
    - Synthesizes a new skill if no near-duplicate exists
    - Records error patterns from failed attempts
    - Blends quality scores on recalled skills

    All operations are best-effort: exceptions are logged and swallowed so
    that learning failures never surface to the caller.
    """

    def __init__(
        self,
        store: IOperationalStore,
        embedder: Any,
    ) -> None:
        self._store = store
        self._synthesizer = SkillSynthesizer(store, embedder)
        self._error_learner = ErrorLearner(store, embedder)
        self._optimizer = QualityOptimizer(store, embedder)

    async def run(self, state: GraphState) -> GraphState:
        reflection: dict[str, Any] = {}

        try:
            reflection["error_learned"] = await self._error_learner.learn(state)
        except Exception as exc:
            logger.debug("error_learner failed: %s", exc)

        pattern = extract_pattern(state)
        if pattern is not None:
            try:
                reflection["skill_synthesized"] = await self._synthesizer.synthesize(pattern)
            except Exception as exc:
                logger.debug("skill_synthesizer failed: %s", exc)

            try:
                reflection["quality_updates"] = await self._optimizer.optimize(state)
            except Exception as exc:
                logger.debug("quality_optimizer failed: %s", exc)

        state.metadata["reflection"] = reflection
        return state
