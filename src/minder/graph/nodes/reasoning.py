from __future__ import annotations

from minder.graph.state import GraphState


class ReasoningNode:
    def run(self, state: GraphState) -> GraphState:
        sources = [
            {"path": doc["path"], "title": doc["title"], "score": doc["score"]}
            for doc in state.reranked_docs
        ]
        snippets = []
        for doc in state.reranked_docs[:3]:
            content = str(doc["content"]).strip()
            snippets.append(f"Source: {doc['path']}\n{content[:240]}")

        guidance = state.workflow_context.get("guidance", "")
        prompt = "\n\n".join(
            [
                guidance,
                f"User query: {state.query}",
                "Retrieved context:",
                "\n\n".join(snippets) if snippets else "No repository context found.",
                "Respond with grounded reasoning and cite source paths.",
            ]
        )
        state.reasoning_output = {
            "prompt": prompt,
            "sources": sources,
            "workflow_instruction": guidance,
        }
        return state
