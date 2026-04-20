from __future__ import annotations

import json

from minder.graph.state import GraphState
from minder.prompts import PromptRegistry
from minder.tools.registry import tool_capability_manifest, tool_data_access_policy


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
        instruction_envelope = state.workflow_context.get("instruction_envelope", {})
        continuity_brief = state.workflow_context.get("continuity_brief", {})
        retry_reason = str(state.metadata.get("retry_reason", "") or "").strip()
        continuity_packet = continuity_brief or {}
        prompt_template = str(
            state.metadata.get("query_prompt_template")
            or (PromptRegistry.get_builtin_definition("query_reasoning") or {}).get(
                "content_template", ""
            )
        )
        prompt_defaults = dict(state.metadata.get("query_prompt_defaults", {}) or {})
        prompt = PromptRegistry.render_content_template(
            prompt_template,
            {
                "workflow_instruction": guidance,
                "instruction_envelope": (
                    json.dumps(
                        instruction_envelope,
                        indent=2,
                        sort_keys=True,
                    )
                    if instruction_envelope
                    else "{}"
                ),
                "continuity_brief": (
                    json.dumps(
                        continuity_brief,
                        indent=2,
                        sort_keys=True,
                    )
                    if continuity_brief
                    else "{}"
                ),
                "continuity_packet": (
                    json.dumps(
                        continuity_packet,
                        indent=2,
                        sort_keys=True,
                    )
                    if continuity_packet
                    else "{}"
                ),
                "tool_capabilities": tool_capability_manifest(),
                "data_access_policy": tool_data_access_policy(),
                "repository_context_note": (
                    "Repository context is available for repo-scoped reasoning."
                    if state.repo_path
                    else "No repository is currently selected. Minder can still describe its built-in tools and internal data capabilities, but repo-scoped code and graph inspection tools need repository context first."
                ),
                "user_query": state.query,
                "retrieved_context": (
                    "\n\n".join(snippets)
                    if snippets
                    else "No repository context found."
                ),
                "correction_required": retry_reason,
            },
            defaults=prompt_defaults,
        )
        state.reasoning_output = {
            "prompt": prompt,
            "sources": sources,
            "workflow_instruction": guidance,
            "prompt_name": state.metadata.get("query_prompt_name", "query_reasoning"),
        }
        return state
