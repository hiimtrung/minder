"""P7-T01 — Extract reusable execution patterns from successful GraphState runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from minder.graph.state import GraphState

_SUCCESS_EDGES = {"complete", "fallback_complete"}
_MIN_QUALITY = 0.5


class PatternExtractor:
    """Stateless extractor: produces a pattern dict from a finished GraphState."""

    def extract(self, state: GraphState) -> dict[str, Any] | None:
        return extract_pattern(state)


def extract_pattern(state: GraphState) -> dict[str, Any] | None:
    """Return a workflow-pattern dict for a successful run, or None to skip."""
    edge = str(state.metadata.get("edge", "") or "")
    quality_score = float((state.evaluation or {}).get("quality_score", 0.0) or 0.0)

    if edge not in _SUCCESS_EDGES or quality_score < _MIN_QUALITY:
        return None

    sources = [
        str(s.get("path", ""))
        for s in (state.reasoning_output or {}).get("sources", [])
        if s.get("path")
    ]
    return {
        "query": state.query,
        "workflow_name": str(state.workflow_context.get("workflow_name", "default")),
        "current_step": str(state.workflow_context.get("current_step", "")),
        "sources_used": sources,
        "edge": edge,
        "quality_score": quality_score,
        "retry_count": int(state.retry_count or 0),
        "llm_provider": str((state.llm_output or {}).get("provider", "")),
        "attempt_count": 1 + int(state.retry_count or 0),
    }
