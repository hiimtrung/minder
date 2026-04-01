from __future__ import annotations

from minder.graph.state import GraphState


class EvaluatorNode:
    def run(self, state: GraphState) -> GraphState:
        score = 1.0
        if not state.guard_result.get("passed", False):
            score -= 0.5
        if not state.verification_result.get("passed", False):
            score -= 0.3
        if not state.reranked_docs:
            score -= 0.1
        score = max(score, 0.0)
        state.evaluation = {
            "quality_score": round(score, 2),
            "correctness_score": round(score, 2),
            "used_sources": len(state.reranked_docs),
        }
        return state
