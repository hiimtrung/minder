from __future__ import annotations

import ast
import re
from re import Pattern
from typing import Any

from minder.graph.state import GraphState

UNSAFE_PATTERNS = ("rm -rf", "DROP TABLE", "ignore all safety", "steal credentials")
SECRET_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)
HIGH_RISK_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bdeploy(?:ment)?\b.*\b(prod|production)\b"),
    re.compile(r"\b(prod|production)\b.*\bdeploy(?:ment)?\b"),
    re.compile(r"\bdrop table\b"),
    re.compile(r"\bdelete\b.*\b(prod|production|database|db)\b"),
    re.compile(r"\brollback\b"),
    re.compile(r"\brotate\b.*\b(secret|credential|token|key)\b"),
    re.compile(r"\bmigrat(?:e|ion)\b.*\b(prod|production|database|db)\b"),
)


class GuardNode:
    def run(self, state: GraphState) -> GraphState:
        text = str(state.llm_output.get("text", ""))
        reasons: list[str] = []
        passed = True
        severity = self._severity_for_state(state)

        lowered = text.lower()
        for pattern in UNSAFE_PATTERNS:
            if pattern.lower() in lowered:
                passed = False
                reasons.append(f"unsafe pattern detected: {pattern}")

        for secret_pattern in SECRET_PATTERNS:
            if secret_pattern.search(text):
                passed = False
                reasons.append("secret or token pattern detected")

        if "```python" in text:
            code = text.split("```python", 1)[1].split("```", 1)[0]
            try:
                ast.parse(code)
            except SyntaxError as exc:
                passed = False
                reasons.append(f"python syntax error: {exc.msg}")

        source_paths = [doc["path"] for doc in state.reranked_docs]
        claimed_sources = state.llm_output.get("sources", [])
        for source in claimed_sources:
            if source not in source_paths:
                passed = False
                reasons.append(f"hallucinated source: {source}")

        instruction_envelope = dict(
            state.workflow_context.get("instruction_envelope", {}) or {}
        )
        output_contract = dict(instruction_envelope.get("output_contract", {}) or {})
        required_markers = [
            str(marker).strip().lower().replace("_", " ")
            for marker in list(output_contract.get("must_include", []) or [])
            if str(marker).strip()
        ]
        normalized_text = lowered.replace("_", " ")
        for marker in required_markers:
            if marker not in normalized_text:
                passed = False
                reasons.append(f"workflow output contract missing: {marker}")

        requires_human = bool(
            state.workflow_context.get("requires_human_approval", False)
        ) or severity == "high"
        human_decision: dict[str, Any] | None = None
        if requires_human:
            from langgraph.types import interrupt

            human_decision = dict(
                interrupt(
                    {
                        "type": "approval_required",
                        "session_id": str(state.session_id) if state.session_id else None,
                        "workflow_step": state.workflow_context.get("current_step"),
                        "artifact_preview": text[:500],
                        "guard_reasons": reasons,
                        "severity": severity,
                    }
                )
                or {}
            )
            if not human_decision.get("approved", False):
                passed = False
                comment = str(human_decision.get("comment", "")).strip()
                reasons.append(comment or "human approval rejected")

        state.guard_result = {
            "passed": passed,
            "reasons": reasons,
            "severity": severity,
            "requires_human_approval": requires_human,
        }
        if human_decision is not None:
            state.guard_result["human_decision"] = human_decision
            if not human_decision.get("approved", False):
                state.guard_result["human_rejected"] = True
        return state

    @staticmethod
    def _severity_for_state(state: GraphState) -> str:
        if bool(state.workflow_context.get("requires_human_approval", False)):
            return "high"
        candidates = [
            str(state.query or ""),
            str(state.llm_output.get("text", "") or ""),
            str(state.workflow_context.get("guidance", "") or ""),
        ]
        payload = state.metadata.get("verification_payload")
        if isinstance(payload, dict):
            candidates.append(str(payload))
        for candidate in candidates:
            lowered = candidate.lower()
            if any(pattern.search(lowered) for pattern in HIGH_RISK_PATTERNS):
                return "high"
        return "normal"
