from __future__ import annotations

from minder.graph.state import GraphState


def determine_next_edge(state: GraphState) -> str:
    # Guard and verification failures must be checked before fallback_used so
    # that a fallback-LLM response that fails guard/verification still triggers
    # the retry loop instead of prematurely exiting as "fallback_complete".
    if state.guard_result.get("passed") is False:
        return "guard_failed"
    if state.verification_result.get("passed") is False:
        return "verification_failed"
    if state.metadata.get("fallback_used") is True:
        return "fallback_complete"
    return "complete"
