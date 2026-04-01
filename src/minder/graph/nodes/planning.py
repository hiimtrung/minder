from __future__ import annotations

from minder.graph.state import GraphState


class PlanningNode:
    def run(self, state: GraphState) -> GraphState:
        query = state.query.lower()
        intent = "explain"
        if any(word in query for word in ("fix", "implement", "write", "generate")):
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
