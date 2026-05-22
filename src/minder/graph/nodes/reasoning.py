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
    instruction_envelope: dict[str, Any],
    continuity_brief: dict[str, Any],
    retry_reason: str,
) -> list[dict[str, Any]]:
    """Build a lean chat messages list for create_chat_completion.

    Excludes the full tool-capability manifest and data-access policy — those
    are only meaningful for MCP tool-call routing, not for dashboard chat answers.
    """
    # Extract only the base step instruction (before the embedded envelope/brief sections).
    step_guidance = guidance.split("\n\nInstruction envelope:")[0].strip() if guidance else ""

    system_parts: list[str] = [
        "You are Minder, a repository-aware engineering assistant.",
        "Answer the user's question with absolute completeness yet extreme conciseness.",
        "Cite specific file paths when referencing code.",
        "To maximize response speed and ensure a purely professional engineering tone:",
        "1. Answer directly and immediately. Prohibit all polite greetings, conversational filler, introductory remarks, closing remarks, and polite honorifics in Vietnamese or English (e.g. NEVER use 'Dạ', 'ạ', 'thưa', 'nhé', 'nha', 'chào', 'rất vui', 'sure', 'here is', 'glad to help').",
        "2. NEVER use exclamation marks (!) or any exclamatory sentences/words. Keep everything strictly declarative and professional.",
    ]
    if step_guidance:
        system_parts.append(f"Workflow guidance: {step_guidance}")

    if instruction_envelope:
        envelope_lines: list[str] = []
        current_step = instruction_envelope.get("current_step", "")
        if current_step:
            envelope_lines.append(f"Step: {current_step}")
        required = instruction_envelope.get("required_artifacts") or []
        if required:
            envelope_lines.append(f"Required artifacts: {', '.join(required)}")
        forbidden = instruction_envelope.get("forbidden_actions") or []
        if forbidden:
            envelope_lines.append(f"Forbidden actions: {', '.join(forbidden)}")
        if envelope_lines:
            system_parts.append("Step constraints:\n" + "\n".join(envelope_lines))

    if continuity_brief:
        brief_lines: list[str] = []
        progress = continuity_brief.get("confirmed_progress") or []
        if progress:
            brief_lines.append(f"Progress: {'; '.join(progress)}")
        blockers = continuity_brief.get("unresolved_blockers") or []
        if blockers:
            brief_lines.append(f"Blockers: {'; '.join(blockers)}")
        next_actions = continuity_brief.get("next_valid_actions") or []
        if next_actions:
            brief_lines.append(f"Next: {'; '.join(next_actions[:2])}")
        if brief_lines:
            system_parts.append("Session context:\n" + "\n".join(brief_lines))

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
    enriched = list(state.metadata.get("enriched_context") or [])
    if enriched:
        user_parts.append(_format_enriched_context(enriched))
    user_parts.append(f"Question: {state.query}")
    messages.append({"role": "user", "content": "\n\n".join(user_parts)})

    return messages


def _build_retrieved_context(snippets: list[str], enriched_items: list[dict]) -> str:
    """Combine code snippets and enriched store items into a single context string."""
    parts: list[str] = []
    if snippets:
        parts.append("\n\n".join(snippets))
    if enriched_items:
        parts.append(_format_enriched_context(enriched_items))
    return "\n\n".join(parts) if parts else "No context found."


def _format_enriched_context(items: list[dict]) -> str:
    """Build a structured knowledge-base section from enriched store items."""
    lines: list[str] = [f"Knowledge base ({len(items)} items):"]
    for i, item in enumerate(items, 1):
        item_type = item.get("type", "item")
        title = item.get("title", "Untitled")
        content = str(item.get("content", "")).strip()
        tags = item.get("tags") or []
        quality = item.get("quality_score", 0.0)
        language = item.get("language", "")

        header = f"[{i}] {item_type.upper()}: {title}"
        if language:
            header += f" ({language})"
        if quality:
            header += f" [quality: {quality:.1f}]"
        if tags:
            header += f" [tags: {', '.join(tags)}]"

        lines.append(header)
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines)


class ReasoningNode:
    def run(self, state: GraphState) -> GraphState:
        reranked = getattr(state, "reranked_docs", []) or []
        retrieved = getattr(state, "retrieved_docs", []) or []
        docs = reranked or retrieved
        sources = [
            {"path": doc["path"], "title": doc["title"], "score": doc["score"]}
            for doc in docs
        ]
        enriched_items = list(state.metadata.get("enriched_context") or [])
        snippets = []
        # Increase snippet count when enriched context supplements code docs
        snippet_limit = 3 if enriched_items else 6
        for doc in docs[:snippet_limit]:
            content = str(doc.get("content", "")).strip()
            snippets.append(f"Source: {doc['path']}\n{content[:500]}")

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
                "retrieved_context": _build_retrieved_context(snippets, enriched_items),
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
            instruction_envelope=dict(instruction_envelope or {}),
            continuity_brief=dict(continuity_brief or {}),
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
