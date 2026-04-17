from __future__ import annotations

import json
import re
from typing import Any

from minder.config import MinderConfig


def normalize_step_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def step_keywords(step_name: str | None) -> set[str]:
    normalized = normalize_step_name(step_name)
    return {
        token
        for token in normalized.replace("/", " ").replace("_", " ").split()
        if token
    }


def required_artifacts_for_step(step_name: str | None) -> list[str]:
    normalized = normalize_step_name(step_name)
    if "problem" in normalized or "intake" in normalized:
        return ["problem_statement", "acceptance_criteria"]
    if "analysis" in normalized or "use case" in normalized:
        return ["analysis_notes", "use_cases"]
    if "test" in normalized:
        return ["test_plan", "failing_tests"]
    if "implement" in normalized:
        return ["implementation_notes", "changed_files"]
    if "verif" in normalized:
        return ["verification_report", "test_results"]
    if "review" in normalized:
        return ["review_notes", "approval_summary"]
    if "release" in normalized or "deploy" in normalized:
        return ["release_notes", "rollback_plan"]
    return ["step_notes"]


def allowed_tools_for_step(step_name: str | None) -> list[str]:
    normalized = normalize_step_name(step_name)
    base_tools = [
        "minder_session_restore",
        "minder_session_save",
        "minder_session_context",
        "minder_memory_recall",
        "minder_workflow_step",
        "minder_workflow_guard",
    ]
    if "test" in normalized:
        return base_tools + ["minder_search_code", "minder_search_errors"]
    if "implement" in normalized:
        return base_tools + ["minder_search_code", "minder_query"]
    if "review" in normalized:
        return base_tools + ["minder_query", "minder_search_code"]
    return base_tools + ["minder_search", "minder_search_code"]


def forbidden_actions_for_step(
    step_name: str | None,
    *,
    blocked_by: list[str],
    current_step: str | None,
) -> list[str]:
    forbidden = ["skip_required_steps", "ignore_workflow_state"]
    if blocked_by:
        forbidden.append("advance_while_blocked")
    if normalize_step_name(step_name) != normalize_step_name(current_step):
        forbidden.append("jump_to_unapproved_step")
    return forbidden


def output_contract_for_step(step_name: str | None) -> dict[str, Any]:
    normalized = normalize_step_name(step_name)
    if "test" in normalized:
        return {
            "type": "test_spec",
            "must_include": ["target_behaviour", "failing_assertions", "scope_limit"],
        }
    if "implement" in normalized:
        return {
            "type": "implementation_update",
            "must_include": ["changed_files", "minimal_fix", "verification_plan"],
        }
    if "review" in normalized:
        return {
            "type": "review_report",
            "must_include": [
                "blocking_issues",
                "recommended_changes",
                "residual_risks",
            ],
        }
    return {
        "type": "step_update",
        "must_include": ["summary", "next_actions"],
    }


def build_instruction_envelope(
    *,
    workflow: Any,
    workflow_state: Any,
) -> dict[str, Any]:
    current_step = getattr(workflow_state, "current_step", None)
    blocked_by = list(getattr(workflow_state, "blocked_by", []) or [])
    artifacts = dict(getattr(workflow_state, "artifacts", {}) or {})
    required_artifacts = required_artifacts_for_step(current_step)
    return {
        "workflow_id": str(getattr(workflow, "id", "")),
        "workflow_version": getattr(workflow, "version", 1),
        "workflow_name": getattr(workflow, "name", ""),
        "current_step": current_step,
        "next_step": getattr(workflow_state, "next_step", None),
        "blocked_by": blocked_by,
        "required_artifacts": required_artifacts,
        "required_artifact_status": {
            artifact_name: artifact_name in artifacts and bool(artifacts[artifact_name])
            for artifact_name in required_artifacts
        },
        "forbidden_actions": forbidden_actions_for_step(
            current_step,
            blocked_by=blocked_by,
            current_step=current_step,
        ),
        "allowed_tools": allowed_tools_for_step(current_step),
        "output_contract": output_contract_for_step(current_step),
        "policies": dict(getattr(workflow, "policies", {}) or {}),
    }


def build_continuity_brief(
    *,
    session: Any,
    workflow_state: Any | None = None,
    workflow: Any | None = None,
    recalled_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = dict(getattr(session, "state", {}) or {})
    project_context = dict(getattr(session, "project_context", {}) or {})
    active_skills = dict(getattr(session, "active_skills", {}) or {})
    blocked_by = (
        list(getattr(workflow_state, "blocked_by", []) or []) if workflow_state else []
    )
    completed_steps = (
        list(getattr(workflow_state, "completed_steps", []) or [])
        if workflow_state
        else []
    )
    current_step = (
        getattr(workflow_state, "current_step", None) if workflow_state else None
    )
    next_step = getattr(workflow_state, "next_step", None) if workflow_state else None

    task = (
        state.get("task")
        or state.get("checkpoint")
        or state.get("phase")
        or "Active engineering task"
    )
    repo_path = project_context.get("repo_path") or project_context.get("repo")
    branch = project_context.get("branch")
    open_files = list(project_context.get("open_files", []) or [])
    state_blockers = state.get("blockers") or state.get("blocked_by") or []
    blockers = [
        str(item) for item in [*blocked_by, *state_blockers] if str(item).strip()
    ]
    next_actions = list(state.get("next_steps", []) or [])
    if not next_actions and next_step:
        next_actions.append(
            f"Advance to {next_step} once current step requirements are satisfied."
        )
    if current_step and not next_actions:
        next_actions.append(f"Complete the remaining artifacts for {current_step}.")

    confirmed_progress: list[str] = []
    if completed_steps:
        confirmed_progress.append(
            f"Completed workflow steps: {', '.join(completed_steps)}"
        )
    if open_files:
        confirmed_progress.append(f"Open files in focus: {', '.join(open_files)}")
    if active_skills:
        confirmed_progress.append(
            f"Active skills: {', '.join(sorted(str(key) for key in active_skills.keys()))}"
        )

    risk_signals: list[str] = []
    if blockers:
        risk_signals.append("workflow_blocked")
    if workflow and getattr(workflow, "enforcement", "") == "strict":
        risk_signals.append("strict_workflow_enforcement")
    if not open_files:
        risk_signals.append("low_editor_context")

    source_refs = [f"session:{getattr(session, 'id', '')}"]
    if workflow_state is not None:
        source_refs.append(f"workflow_state:{getattr(workflow_state, 'id', '')}")
    if recalled_memories:
        source_refs.extend(
            f"memory:{item['id']}" for item in recalled_memories[:3] if item.get("id")
        )

    return {
        "problem_framing": {
            "task": task,
            "repo_path": repo_path,
            "branch": branch,
            "workflow_step": current_step,
        },
        "confirmed_progress": confirmed_progress,
        "unresolved_blockers": blockers,
        "risk_signals": risk_signals,
        "next_valid_actions": next_actions,
        "source_references": source_refs,
    }


def compatibility_score_for_memory(
    *,
    tags: list[str],
    title: str,
    content: str,
    current_step: str | None,
    artifact_type: str | None,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    normalized_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
    text = f"{title} {content}".lower()

    if current_step:
        step_words = step_keywords(current_step)
        if step_words & normalized_tags:
            score += 1.0
            reasons.append("tag_matches_workflow_step")
        elif any(word in text for word in step_words):
            score += 0.6
            reasons.append("content_mentions_workflow_step")

    if artifact_type:
        normalized_artifact = artifact_type.strip().lower()
        if normalized_artifact in normalized_tags:
            score += 0.5
            reasons.append("tag_matches_artifact_type")
        elif normalized_artifact in text:
            score += 0.3
            reasons.append("content_mentions_artifact_type")

    return min(score, 1.5), reasons


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not raw.strip():
        return None
    candidates = re.findall(r"\{.*\}", raw, flags=re.DOTALL)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


class ContinuitySynthesizer:
    def __init__(self, config: MinderConfig) -> None:
        from minder.llm.local import LocalModelLLM

        self._config = config
        self._llm = LocalModelLLM(config.llm.model_path, runtime="auto")

    def synthesize_memory_hits(
        self,
        *,
        query: str,
        hits: list[dict[str, Any]],
        current_step: str | None,
        artifact_type: str | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        fallback = self._memory_hits_fallback(
            query=query,
            hits=hits,
            current_step=current_step,
            artifact_type=artifact_type,
        )
        prompt = "\n\n".join(
            [
                "You are synthesizing recalled engineering memories for a workflow-aware assistant.",
                "Return only valid JSON with keys: summary, focus, recommended_hit_ids, hit_summaries.",
                "Keep hit_summaries as an object keyed by hit id.",
                f"Current workflow step: {current_step or 'unknown'}",
                f"Artifact type: {artifact_type or 'unknown'}",
                f"User recall query: {query}",
                f"Hits: {json.dumps(hits[:5], ensure_ascii=True, indent=2)}",
            ]
        )
        raw = self._llm.complete_text(
            prompt,
            max_tokens=700,
            temperature=min(max(self._config.llm.temperature, 0.05), 0.3),
            fallback="",
        )
        parsed = _extract_json_object(raw)
        if not parsed:
            return fallback, {
                "provider": "heuristic",
                "model": self._config.llm.model_name,
                "runtime": self._llm.runtime,
            }
        return {
            "summary": str(parsed.get("summary", fallback["summary"]))
            or fallback["summary"],
            "focus": str(parsed.get("focus", fallback["focus"])) or fallback["focus"],
            "recommended_hit_ids": list(
                parsed.get("recommended_hit_ids", fallback["recommended_hit_ids"])
            ),
            "hit_summaries": {
                str(key): str(value)
                for key, value in dict(
                    parsed.get("hit_summaries", fallback["hit_summaries"]) or {}
                ).items()
            },
        }, {
            "provider": "local_llm",
            "model": "gemma-4-e2b-it",
            "runtime": self._llm.runtime,
        }

    def _memory_hits_fallback(
        self,
        *,
        query: str,
        hits: list[dict[str, Any]],
        current_step: str | None,
        artifact_type: str | None,
    ) -> dict[str, Any]:
        focus = current_step or artifact_type or "general retrieval"
        recommended_ids = [str(hit.get("id", "")) for hit in hits[:2] if hit.get("id")]
        hit_summaries = {
            str(hit.get("id", "")): (
                f"Use {hit.get('title', 'this memory')} for {focus}; reasons: {', '.join(hit.get('continuity_reasons', [])) or 'semantic match'}"
            )
            for hit in hits[:5]
            if hit.get("id")
        }
        top_titles = (
            ", ".join(str(hit.get("title", "")) for hit in hits[:2] if hit.get("title"))
            or "no strong hits"
        )
        return {
            "summary": f"Top recalled memories for '{query}' focus on {focus}: {top_titles}.",
            "focus": focus,
            "recommended_hit_ids": recommended_ids,
            "hit_summaries": hit_summaries,
        }
