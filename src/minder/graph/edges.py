from __future__ import annotations

from minder.graph.state import GraphState


def determine_next_edge(state: GraphState) -> str:
    if state.metadata.get("fallback_used") is True:
        return "fallback_complete"
    if state.guard_result.get("passed") is False:
        return "guard_failed"
    if state.verification_result.get("passed") is False:
        return "verification_failed"
    return "complete"
