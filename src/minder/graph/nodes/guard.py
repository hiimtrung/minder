from __future__ import annotations

import ast
import re
from re import Pattern

from minder.graph.state import GraphState

UNSAFE_PATTERNS = ("rm -rf", "DROP TABLE", "ignore all safety", "steal credentials")
SECRET_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)


class GuardNode:
    def run(self, state: GraphState) -> GraphState:
        text = str(state.llm_output.get("text", ""))
        reasons: list[str] = []
        passed = True

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

        state.guard_result = {"passed": passed, "reasons": reasons}
        return state
