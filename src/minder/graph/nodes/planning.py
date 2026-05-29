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

    # Single-word tokens checked against the word-set of the query.
    _CONVERSATIONAL_WORDS = frozenset({
        "hello", "hi", "hey", "chào", "howdy", "greetings",
        "thanks", "ty", "thx", "cảm", "ok", "okay", "alright",
        "sup", "yo", "bye", "goodbye", "ciao", "tạm",
    })

    # Multi-word phrases checked via substring search (after lower + strip).
    _CONVERSATIONAL_PHRASES = (
        "xin chào", "good morning", "good afternoon", "good evening",
        "good night", "how are you", "how are u", "how r u",
        "how's it going", "hows it going", "what's up", "what's new",
        "thank you", "cảm ơn", "tạm biệt", "have a good",
        "nice to meet", "i'm back", "just saying hi",
    )

    def run(self, state: GraphState) -> GraphState:
        query = state.query.lower().strip()
        intent = "explain"

        # Short conversational messages — detect by word-token or phrase match.
        # Cap at 10 words: longer queries always have real intent even if they
        # contain a greeting word.
        query_words = set(query.split())
        if len(query.split()) <= 10 and (
            query_words & self._CONVERSATIONAL_WORDS
            or any(phrase in query for phrase in self._CONVERSATIONAL_PHRASES)
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
