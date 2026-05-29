from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

from langgraph.graph import END, StateGraph

if TYPE_CHECKING:
    from minder.application.skills.service import SkillService
    from minder.config import MinderConfig


class SkillRecallState(TypedDict):
    original_query: str
    current_step: str | None
    artifact_type: str | None
    target_count: int
    min_quality_score: float
    raw_items: list[dict[str, Any]]
    final_items: list[dict[str, Any]]
    summary: str


class AgenticSkillGraph:
    """Agentic RAG graph for skill recall.

    Flow: recall → rag_refine → END

    The recall node fetches candidates (2x target_count to give the LLM room to filter).
    The rag_refine node passes raw candidates through the local LLM to remove noise and
    produce a concise summary, then trims to target_count.
    """

    def __init__(self, skill_service: SkillService, config: MinderConfig) -> None:
        self._service = skill_service
        self._config = config
        self._refiner: Any = None
        self._compiled = self._build().compile()

    def _get_refiner(self) -> Any:
        if self._refiner is None:
            from minder.application.rag_refiner import RAGRefiner

            self._refiner = RAGRefiner(self._config)
        return self._refiner

    async def run(self, state: SkillRecallState) -> SkillRecallState:
        result = await self._compiled.ainvoke(state)
        return cast(SkillRecallState, result if isinstance(result, dict) else dict(result))

    def _build(self) -> StateGraph:
        workflow = StateGraph(SkillRecallState)
        workflow.add_node("recall", self._recall_node)
        workflow.add_node("rag_refine", self._rag_refine_node)
        workflow.set_entry_point("recall")
        workflow.add_edge("recall", "rag_refine")
        workflow.add_edge("rag_refine", END)
        return workflow

    async def _recall_node(self, state: SkillRecallState) -> dict[str, Any]:
        raw = await self._service._skill_recall_candidates(  # noqa: SLF001
            state["original_query"],
            limit=max(state["target_count"] * 2, state["target_count"] + 5),
            current_step=state.get("current_step"),
            artifact_type=state.get("artifact_type"),
            min_quality_score=float(state.get("min_quality_score", 0.0)),
        )
        return {"raw_items": raw}

    def _rag_refine_node(self, state: SkillRecallState) -> dict[str, Any]:
        raw = list(state.get("raw_items", []))
        context_parts: list[str] = []
        if state.get("current_step"):
            context_parts.append(f"Workflow step: {state['current_step']}")
        if state.get("artifact_type"):
            context_parts.append(f"Artifact type: {state['artifact_type']}")
        context = " | ".join(context_parts) or None

        filtered, summary = self._get_refiner().refine(
            query=state["original_query"],
            items=raw,
            context=context,
        )
        final = filtered[: state["target_count"]]
        for item in final:
            item["step_compatibility"] = item.pop("_step_compat", 0.0)
        return {"final_items": final, "summary": summary}
