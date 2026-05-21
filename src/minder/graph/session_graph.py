from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, TypedDict, cast

from langgraph.graph import END, StateGraph

from minder.continuity import (
    _extract_json_object,
    build_continuity_brief,
    build_instruction_envelope,
    compatibility_score_for_memory,
)

if TYPE_CHECKING:
    from minder.config import MinderConfig
    from minder.tools.memory import MemoryTools
    from minder.tools.session import SessionTools


class SessionRestoreState(TypedDict):
    session_id: str
    session_model: Any
    workflow_model: Any
    workflow_state_model: Any
    session_name: str | None
    session_state: dict[str, Any]
    workflow_step: str | None
    workflow_context: dict[str, Any]
    project_context: dict[str, Any]
    active_skills: dict[str, Any]
    recalled_memories: list[dict[str, Any]]
    coherence_result: dict[str, Any]
    unified_context: dict[str, Any]


class SessionContextGraph:
    def __init__(
        self,
        session_tools: SessionTools,
        memory_tools: MemoryTools,
        config: MinderConfig,
    ) -> None:
        self._session_tools = session_tools
        self._memory_tools = memory_tools
        self._config = config
        self._compiled = self._build().compile()
        self._judge_llm = self._build_judge_llm()

    async def run(self, state: SessionRestoreState) -> SessionRestoreState:
        result = await self._compiled.ainvoke(state)
        return cast(
            SessionRestoreState,
            result if isinstance(result, dict) else dict(result),
        )

    def _build(self) -> StateGraph:
        workflow = StateGraph(SessionRestoreState)
        workflow.add_node("load_session", self._load_session)
        workflow.add_node("targeted_recall", self._targeted_recall)
        workflow.add_node("coherence_check", self._coherence_check)
        workflow.add_node("build_context", self._build_context)
        workflow.set_entry_point("load_session")
        workflow.add_edge("load_session", "targeted_recall")
        workflow.add_edge("targeted_recall", "coherence_check")
        workflow.add_edge("coherence_check", "build_context")
        workflow.add_edge("build_context", END)
        return workflow

    def _build_judge_llm(self) -> Any | None:
        try:
            from minder.llm.factory import create_llm

            llm = create_llm(self._config.llm)
        except Exception:
            return None
        return llm if hasattr(llm, "complete_text") else None

    async def _load_session(self, state: SessionRestoreState) -> dict[str, Any]:
        import uuid

        session = await self._session_tools._require_active_session(  # noqa: SLF001
            uuid.UUID(state["session_id"])
        )
        workflow = None
        workflow_state = None
        workflow_step = None
        workflow_context: dict[str, Any] = {}
        if session.repo_id is not None:
            repo = await self._session_tools._store.get_repository_by_id(session.repo_id)  # noqa: SLF001
            workflow_state = await self._session_tools._store.get_workflow_state_by_repo(  # noqa: SLF001
                session.repo_id
            )
            if workflow_state is not None:
                workflow_step = getattr(workflow_state, "current_step", None)
            if repo is not None and repo.workflow_id is not None:
                workflow = await self._session_tools._store.get_workflow_by_id(repo.workflow_id)  # noqa: SLF001
            workflow_context = {
                "repo_id": str(session.repo_id),
                "workflow_id": str(getattr(workflow, "id", "")) if workflow else None,
            }
        return {
            "session_model": session,
            "workflow_model": workflow,
            "workflow_state_model": workflow_state,
            "session_name": getattr(session, "name", None),
            "session_state": dict(getattr(session, "state", {}) or {}),
            "workflow_step": workflow_step,
            "workflow_context": workflow_context,
            "project_context": dict(getattr(session, "project_context", {}) or {}),
            "active_skills": dict(getattr(session, "active_skills", {}) or {}),
        }

    async def _targeted_recall(self, state: SessionRestoreState) -> dict[str, Any]:
        queries = self.build_targeted_queries(
            session_state=state.get("session_state", {}),
            workflow_step=state.get("workflow_step"),
            project_context=state.get("project_context", {}),
        )
        if not queries:
            return {"recalled_memories": []}
        per_query_limit = max(
            2,
            int(self._config.session.restore_recall_count / max(len(queries), 1)),
        )
        recalled: list[dict[str, Any]] = []
        for query in queries:
            hits = await self._memory_tools.minder_memory_recall(
                query,
                limit=per_query_limit,
                current_step=state.get("workflow_step"),
            )
            recalled.extend(hits)
        return {
            "recalled_memories": self._dedupe_memories(recalled)[
                : self._config.session.restore_recall_count
            ]
        }

    def _coherence_check(self, state: SessionRestoreState) -> dict[str, Any]:
        heuristic = self._heuristic_coherence(state)
        llm_result = self._judge_with_llm(state, heuristic)
        return {"coherence_result": llm_result or heuristic}

    def _build_context(self, state: SessionRestoreState) -> dict[str, Any]:
        coherence = dict(state.get("coherence_result") or {})
        stale_ids = set(str(item) for item in coherence.get("stale_memories", []))
        filtered_memories = [
            item
            for item in state.get("recalled_memories", [])
            if str(item.get("id", "")) not in stale_ids
        ]
        relevant_memories = filtered_memories or list(state.get("recalled_memories", []))

        continuity_packet: dict[str, Any] | None = None
        workflow = state.get("workflow_model")
        workflow_state = state.get("workflow_state_model")
        session = state.get("session_model")
        if workflow is not None and workflow_state is not None and session is not None:
            continuity_packet = {
                "instruction_envelope": build_instruction_envelope(
                    workflow=workflow,
                    workflow_state=workflow_state,
                ),
                "session_brief": build_continuity_brief(
                    session=session,
                    workflow_state=workflow_state,
                    workflow=workflow,
                    recalled_memories=relevant_memories,
                ),
            }

        warnings = [str(item) for item in coherence.get("contradictions", []) if item]
        warnings.extend(
            f"stale_memory:{memory_id}"
            for memory_id in coherence.get("stale_memories", [])
            if memory_id
        )
        repo_id = state.get("workflow_context", {}).get("repo_id") or None
        payload: dict[str, Any] = {
            "session_id": state["session_id"],
            "name": state.get("session_name"),
            "repo_id": repo_id,
            "state": state.get("session_state", {}),
            "active_skills": state.get("active_skills", {}),
            "project_context": state.get("project_context", {}),
            "workflow_step": state.get("workflow_step"),
            "relevant_memories": relevant_memories,
            "coherence_warnings": warnings,
            "context_confidence": float(coherence.get("confidence", 0.0)),
        }
        if continuity_packet is not None:
            payload["continuity_packet"] = continuity_packet
        return {"unified_context": payload}

    def _heuristic_coherence(self, state: SessionRestoreState) -> dict[str, Any]:
        project_context = dict(state.get("project_context", {}) or {})
        session_state = dict(state.get("session_state", {}) or {})
        workflow_step = state.get("workflow_step")
        branch = str(project_context.get("branch", "") or "").strip()
        task_text = " ".join(
            str(session_state.get(key, "") or "")
            for key in ("task", "checkpoint", "phase")
        ).lower()
        contradictions: list[str] = []
        stale_memories: list[str] = []
        for memory in state.get("recalled_memories", []):
            memory_id = str(memory.get("id", ""))
            text = " ".join(
                [
                    str(memory.get("title", "") or ""),
                    str(memory.get("content", "") or ""),
                    " ".join(str(tag) for tag in memory.get("tags", []) or []),
                ]
            ).lower()
            tags = [str(tag) for tag in memory.get("tags", []) or []]
            compatibility_score, _ = compatibility_score_for_memory(
                tags=tags,
                title=str(memory.get("title", "") or ""),
                content=str(memory.get("content", "") or ""),
                current_step=workflow_step,
                artifact_type=None,
            )
            if compatibility_score <= 0.0 and float(memory.get("score", 0.0)) < 0.5:
                stale_memories.append(memory_id)

            if branch:
                branch_refs = {
                    item for item in _BRANCH_PATTERN.findall(text) if item != branch.lower()
                }
                if branch_refs:
                    contradictions.append(
                        f"memory {memory_id} references branch {sorted(branch_refs)[0]} instead of {branch}"
                    )
            if "jwt" in task_text and "cookie" in text and "jwt" not in text:
                contradictions.append(
                    f"memory {memory_id} may conflict with JWT-oriented session task"
                )
            if "cookie" in task_text and "jwt" in text and "cookie" not in text:
                contradictions.append(
                    f"memory {memory_id} may conflict with cookie-oriented session task"
                )

        contradictions = list(dict.fromkeys(contradictions))
        stale_memories = list(dict.fromkeys(memory_id for memory_id in stale_memories if memory_id))
        confidence = max(
            0.1,
            0.95 - (0.2 * len(contradictions)) - (0.05 * len(stale_memories)),
        )
        return {
            "coherent": not contradictions,
            "contradictions": contradictions,
            "stale_memories": stale_memories,
            "confidence": round(confidence, 4),
        }

    def _judge_with_llm(
        self,
        state: SessionRestoreState,
        fallback: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._judge_llm is None or not state.get("recalled_memories"):
            return None
        prompt = "\n\n".join(
            [
                "You are validating whether restored session context and recalled memories are coherent.",
                "Return only valid JSON with keys: coherent, contradictions, stale_memories, confidence.",
                f"Workflow step: {state.get('workflow_step') or 'unknown'}",
                f"Session state: {json.dumps(state.get('session_state', {}), ensure_ascii=True, indent=2)}",
                f"Project context: {json.dumps(state.get('project_context', {}), ensure_ascii=True, indent=2)}",
                f"Memories: {json.dumps(state.get('recalled_memories', [])[:5], ensure_ascii=True, indent=2)}",
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
        return {
            "coherent": bool(parsed.get("coherent", fallback["coherent"])),
            "contradictions": [
                str(item)
                for item in list(parsed.get("contradictions", fallback["contradictions"]))
            ],
            "stale_memories": [
                str(item)
                for item in list(parsed.get("stale_memories", fallback["stale_memories"]))
            ],
            "confidence": float(parsed.get("confidence", fallback["confidence"])),
        }

    @staticmethod
    def build_targeted_queries(
        *,
        session_state: dict[str, Any],
        workflow_step: str | None,
        project_context: dict[str, Any],
    ) -> list[str]:
        queries: list[str] = []
        task = str(
            session_state.get("task")
            or session_state.get("checkpoint")
            or session_state.get("phase")
            or ""
        ).strip()
        if task:
            query = task
            if workflow_step:
                query = f"{query} {workflow_step}"
            queries.append(query.strip())
        if workflow_step:
            queries.append(f"best practices for {workflow_step} phase")
            queries.append(f"artifacts required in {workflow_step}")
        branch = str(project_context.get("branch", "") or "").strip()
        if branch:
            queries.append(f"context for branch {branch}")
        seen: set[str] = set()
        deduped: list[str] = []
        for query in queries:
            normalized = query.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped[:3]

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
            key=lambda item: float(item.get("score", 0.0)),
            reverse=True,
        )


_BRANCH_PATTERN = re.compile(r"\b[a-z0-9._-]+/[a-z0-9._-]+\b")
