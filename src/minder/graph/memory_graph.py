from __future__ import annotations

import json
import operator
from statistics import fmean
from typing import TYPE_CHECKING, Annotated, Any, TypedDict, cast

from langgraph.graph import END, StateGraph

from minder.continuity import _extract_json_object
from minder.observability.metrics import record_continuity_recall

if TYPE_CHECKING:
    from minder.config import MinderConfig
    from minder.tools.memory import MemoryTools


class MemoryRecallState(TypedDict):
    original_query: str
    current_step: str | None
    artifact_type: str | None
    target_count: int
    min_score: float
    all_memories: Annotated[list[dict[str, Any]], operator.add]
    search_queries: Annotated[list[str], operator.add]
    current_query: str
    iteration: int
    max_iterations: int
    latest_memories: list[dict[str, Any]]
    verdict: dict[str, Any]
    final_memories: list[dict[str, Any]]
    recall_summary: str


class AgenticMemoryGraph:
    def __init__(self, memory_tools: MemoryTools, config: MinderConfig) -> None:
        self._memory_tools = memory_tools
        self._config = config
        self._compiled = self._build().compile()
        self._judge_llm = self._build_judge_llm()

    async def run(self, state: MemoryRecallState) -> MemoryRecallState:
        result = await self._compiled.ainvoke(state)
        return cast(
            MemoryRecallState,
            result if isinstance(result, dict) else dict(result),
        )

    def _build(self) -> StateGraph:
        workflow = StateGraph(MemoryRecallState)
        workflow.add_node("recall", self._recall_node)
        workflow.add_node("judge", self._judge_node)
        workflow.add_node("refine", self._refine_node)
        workflow.add_node("merge", self._merge_node)
        workflow.set_entry_point("recall")
        workflow.add_edge("recall", "judge")
        workflow.add_conditional_edges(
            "judge",
            self._judge_router,
            {"refine": "refine", "merge": "merge"},
        )
        workflow.add_edge("refine", "recall")
        workflow.add_edge("merge", END)
        return workflow

    def _build_judge_llm(self) -> Any | None:
        try:
            from minder.llm.factory import create_llm

            llm = create_llm(self._config.llm)
        except Exception:
            return None
        return llm if hasattr(llm, "complete_text") else None

    async def _recall_node(self, state: MemoryRecallState) -> dict[str, Any]:
        limit = max(state["target_count"] * 3, state["target_count"])
        latest = await self._memory_tools._recall_candidates(  # noqa: SLF001
            state["current_query"],
            limit=limit,
            current_step=state.get("current_step"),
            artifact_type=state.get("artifact_type"),
            include_raw_scores=True,
        )
        return {
            "latest_memories": latest,
            "all_memories": latest,
            "search_queries": [state["current_query"]],
        }

    def _judge_node(self, state: MemoryRecallState) -> dict[str, Any]:
        aggregate = self._dedupe_memories(state.get("all_memories", []))
        heuristic = self._heuristic_verdict(state, aggregate)
        llm_verdict = self._judge_with_llm(state, aggregate, heuristic)
        return {"verdict": llm_verdict or heuristic}

    def _judge_router(self, state: MemoryRecallState) -> str:
        verdict = dict(state.get("verdict") or {})
        if verdict.get("sufficient"):
            return "merge"
        if int(state.get("iteration", 0)) + 1 >= int(state.get("max_iterations", 1)):
            return "merge"
        return "refine"

    def _refine_node(self, state: MemoryRecallState) -> dict[str, Any]:
        verdict = dict(state.get("verdict") or {})
        next_query = str(verdict.get("next_query") or state["original_query"]).strip()
        if not next_query:
            next_query = state["original_query"]
        if next_query in set(state.get("search_queries", [])):
            next_query = self._fallback_refined_query(
                original_query=state["original_query"],
                current_query=state["current_query"],
                current_step=state.get("current_step"),
                artifact_type=state.get("artifact_type"),
                reason=str(verdict.get("reason", "")),
            )
        return {
            "current_query": next_query,
            "iteration": int(state.get("iteration", 0)) + 1,
        }

    def _merge_node(self, state: MemoryRecallState) -> dict[str, Any]:
        final_memories = self._dedupe_memories(state.get("all_memories", []))[
            : state["target_count"]
        ]
        synthesis, synthesis_meta = self._memory_tools._get_synthesizer().synthesize_memory_hits(  # noqa: SLF001
            query=state["original_query"],
            hits=final_memories,
            current_step=state.get("current_step"),
            artifact_type=state.get("artifact_type"),
        )
        for item in final_memories:
            item["recall_summary"] = synthesis["summary"]
            item["hit_summary"] = synthesis["hit_summaries"].get(str(item["id"]), "")
            record_continuity_recall(
                provider=str(synthesis_meta.get("provider", "unknown")),
                step_compatibility=float(item.get("_step_compat", 0.0)),
            )
            item["step_compatibility"] = item.pop("_step_compat", 0.0)
        return {
            "final_memories": final_memories,
            "recall_summary": synthesis["summary"],
        }

    def _heuristic_verdict(
        self,
        state: MemoryRecallState,
        memories: list[dict[str, Any]],
    ) -> dict[str, Any]:
        target_count = max(int(state.get("target_count", 1)), 1)
        top = memories[:target_count]
        scores = [float(item.get("score", 0.0)) for item in top]
        avg_score = fmean(scores) if scores else 0.0
        step_hits = [
            item for item in top if float(item.get("_step_compat", 0.0)) > 0.0
        ]
        sufficient = bool(top) and avg_score >= float(state.get("min_score", 0.0))
        sufficient = sufficient and (
            len(top) >= target_count or len(step_hits) >= max(1, target_count - 1)
        )
        reason = "ok"
        missing_aspects = ""
        if not top:
            reason = "low_coverage"
            missing_aspects = "no relevant memories yet"
        elif avg_score < float(state.get("min_score", 0.0)):
            reason = "low_score"
            missing_aspects = "higher confidence retrieval"
        elif state.get("current_step") and not step_hits:
            reason = "step_mismatch"
            missing_aspects = f"workflow step {state['current_step']}"
            sufficient = False
        elif len(top) < target_count:
            reason = "low_coverage"
            missing_aspects = "additional corroborating memories"
            sufficient = False
        next_query = self._fallback_refined_query(
            original_query=state["original_query"],
            current_query=state["current_query"],
            current_step=state.get("current_step"),
            artifact_type=state.get("artifact_type"),
            reason=reason,
        )
        return {
            "sufficient": sufficient,
            "reason": reason,
            "missing_aspects": missing_aspects,
            "next_query": next_query,
            "confidence": round(min(max(avg_score, 0.0), 1.0), 4),
        }

    def _judge_with_llm(
        self,
        state: MemoryRecallState,
        memories: list[dict[str, Any]],
        fallback: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._judge_llm is None or not memories:
            return None
        prompt = "\n\n".join(
            [
                "You are judging retrieved engineering memories for a workflow-aware assistant.",
                "Return only valid JSON with keys: sufficient, reason, missing_aspects, next_query, confidence.",
                f"Original query: {state['original_query']}",
                f"Current workflow step: {state.get('current_step') or 'unknown'}",
                f"Artifact type: {state.get('artifact_type') or 'unknown'}",
                f"Minimum average score: {state.get('min_score', 0.0)}",
                f"Retrieved memories: {json.dumps(memories[:5], ensure_ascii=True, indent=2)}",
            ]
        )
        try:
            raw = self._judge_llm.complete_text(  # type: ignore[union-attr]
                prompt,
                max_tokens=512,
                temperature=min(max(self._config.llm.temperature, 0.0), 0.2),
                fallback="",
            )
        except Exception:
            return None
        parsed = _extract_json_object(raw)
        if not parsed:
            return None
        verdict = {
            "sufficient": bool(parsed.get("sufficient", fallback["sufficient"])),
            "reason": str(parsed.get("reason", fallback["reason"])) or fallback["reason"],
            "missing_aspects": str(
                parsed.get("missing_aspects", fallback["missing_aspects"])
            ),
            "next_query": str(parsed.get("next_query", fallback["next_query"]))
            or fallback["next_query"],
            "confidence": float(parsed.get("confidence", fallback["confidence"])),
        }
        if verdict["next_query"] in set(state.get("search_queries", [])):
            verdict["next_query"] = fallback["next_query"]
        return verdict

    def _fallback_refined_query(
        self,
        *,
        original_query: str,
        current_query: str,
        current_step: str | None,
        artifact_type: str | None,
        reason: str,
    ) -> str:
        terms = [original_query]
        if reason in {"step_mismatch", "low_coverage"} and current_step:
            terms.append(current_step)
        if artifact_type:
            terms.append(artifact_type)
        if reason == "low_score":
            terms.append("specific implementation details")
        if current_query not in terms:
            terms.append(current_query)
        return " ".join(term.strip() for term in terms if term and term.strip())

    @staticmethod
    def _dedupe_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for memory in memories:
            memory_id = str(memory.get("id", ""))
            if not memory_id:
                continue
            existing = deduped.get(memory_id)
            if existing is None or float(memory.get("score", 0.0)) > float(
                existing.get("score", 0.0)
            ):
                deduped[memory_id] = dict(memory)
        return sorted(
            deduped.values(),
            key=lambda item: (
                float(item.get("score", 0.0)),
                float(item.get("_step_compat", 0.0)),
            ),
            reverse=True,
        )
