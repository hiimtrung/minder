from __future__ import annotations

from minder.graph.state import GraphState


class PlanningNode:
    _CORRECTION_PHRASES = (
        "fix memory", "update memory", "wrong memory", "incorrect memory",
        "outdated memory", "sai memory", "fix skill", "update skill",
        "wrong skill", "outdated skill", "deprecate skill", "mark deprecated",
        "delete memory", "delete skill", "remove memory", "remove skill",
        "correct this", "sửa memory", "cập nhật skill", "xóa memory",
        "xóa skill", "sửa skill",
    )

    def run(self, state: GraphState) -> GraphState:
        query = state.query.lower()
        intent = "explain"
        if any(phrase in query for phrase in self._CORRECTION_PHRASES):
            intent = "correction"
        elif any(word in query for word in ("fix", "implement", "write", "generate")):
            intent = "code_gen"
        elif any(word in query for word in ("debug", "bug", "trace", "error")):
            intent = "debug"
        elif "refactor" in query:
            intent = "refactor"
        elif any(word in query for word in ("search", "find", "look up")):
            intent = "search"

        retrieval_strategy = "hybrid"
        if intent == "search":
            retrieval_strategy = "lexical"
        complexity = "high" if len(query.split()) > 12 else "medium"

        state.plan = {
            "intent": intent,
            "knowledge_layer": "repository",
            "retrieval_strategy": retrieval_strategy,
            "complexity": complexity,
        }
        return state
