from __future__ import annotations

import json
from typing import Any

from minder.graph.state import GraphState
from minder.prompts import PromptRegistry
from minder.tools.registry import tool_capability_manifest, tool_data_access_policy


def _build_chat_messages(
    *,
    state: GraphState,
    snippets: list[str],
    guidance: str,
    retry_reason: str,
) -> list[dict[str, Any]]:
    """Build a lean chat messages list for create_chat_completion.

    Excludes the full tool-capability manifest and data-access policy — those
    are only meaningful for MCP tool-call routing, not for dashboard chat answers.
    """
    system_parts: list[str] = [
        "You are Minder, a repository-aware engineering assistant. "
        "Answer the user's question clearly and concisely. "
        "Cite specific file paths when referencing code."
    ]
    if guidance and guidance.strip():
        system_parts.append(f"Workflow guidance: {guidance.strip()}")
    system_parts.append(
        "A repository is available for code inspection."
        if state.repo_path
        else "No repository is currently selected. Answer from the conversation context and general knowledge."
    )
    if retry_reason:
        system_parts.append(
            f"Your previous answer was rejected. Reason: {retry_reason}. Please correct it."
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)}
    ]

    for h in state.chat_history or []:
        raw_role = str(h.get("role", "user"))
        role = "assistant" if raw_role in ("assistant", "model") else "user"
        content = str(h.get("content", "")).strip()
        if content:
            messages.append({"role": role, "content": content})

    user_parts: list[str] = []
    if snippets:
        user_parts.append(
            "Relevant code from the repository:\n" + "\n\n".join(snippets)
        )
    user_parts.append(f"Question: {state.query}")
    messages.append({"role": "user", "content": "\n\n".join(user_parts)})

    return messages


class ReasoningNode:
    def run(self, state: GraphState) -> GraphState:
        reranked = getattr(state, "reranked_docs", []) or []
        retrieved = getattr(state, "retrieved_docs", []) or []
        docs = reranked or retrieved
        sources = [
            {"path": doc["path"], "title": doc["title"], "score": doc["score"]}
            for doc in docs
        ]
        snippets = []
        for doc in docs[:3]:
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
                "chat_history": (
                    "\n".join(
                        f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content')}"
                        for m in (state.chat_history or [])
                    )
                    if state.chat_history
                    else "No conversation history."
                ),
            },
            defaults=prompt_defaults,
        )
        agent_system_prompt = str(state.metadata.get("agent_system_prompt", "") or "").strip()
        if agent_system_prompt:
            prompt = f"{agent_system_prompt}\n\n{prompt}"

        # Strip large content field from docs now that snippets are extracted
        if state.retrieved_docs:
            state.retrieved_docs = [
                {k: v for k, v in doc.items() if k != "content"}
                for doc in state.retrieved_docs
            ]
        if state.reranked_docs:
            state.reranked_docs = [
                {k: v for k, v in doc.items() if k != "content"}
                for doc in state.reranked_docs
            ]

        chat_messages = _build_chat_messages(
            state=state,
            snippets=snippets,
            guidance=guidance,
            retry_reason=retry_reason,
        )

        state.reasoning_output = {
            "prompt": prompt,
            "messages": chat_messages,
            "sources": sources,
            "workflow_instruction": guidance,
            "prompt_name": state.metadata.get("query_prompt_name", "query_reasoning"),
        }
        return state
