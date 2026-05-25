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

    _CONVERSATIONAL = (
        "hello", "hi", "hey", "chào", "xin chào", "good morning",
        "good afternoon", "good evening", "how are you", "what's up",
        "sup", "yo", "thanks", "thank you", "cảm ơn", "bye", "goodbye",
        "tạm biệt",
    )

    def run(self, state: GraphState) -> GraphState:
        query = state.query.lower().strip()
        intent = "explain"

        # Short conversational messages bypass the heavy agent/retrieval pipeline.
        # Use word-boundary matching for single-word phrases to avoid false positives
        # (e.g. "hi" matching inside "this").
        query_words = set(query.split())
        if len(query.split()) <= 6 and any(
            (phrase in query_words if " " not in phrase else phrase in query)
            for phrase in self._CONVERSATIONAL
        ):
            intent = "chat"

        if intent != "chat":
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
        elif intent == "chat":
            retrieval_strategy = "none"
        complexity = "high" if len(query.split()) > 12 else "medium"
        current_step = str(state.workflow_context.get("current_step", "") or "").lower()
        # Only route to specialist agents for non-conversational queries.
        required_agents: list[str] = []
        if intent != "chat":
            if "review" in current_step or "review" in query:
                required_agents.append("code_reviewer")
            elif "test" in current_step or "test" in query:
                required_agents.append("tester")

        state.plan = {
            "intent": intent,
            "knowledge_layer": "repository",
            "retrieval_strategy": retrieval_strategy,
            "complexity": complexity,
            "required_agents": required_agents,
        }
        return state
