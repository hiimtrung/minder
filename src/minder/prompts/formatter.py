from __future__ import annotations

import json
import re
from dataclasses import dataclass

from minder.config import MinderConfig


@dataclass(slots=True)
class PromptDraft:
    name: str
    title: str
    description: str
    content_template: str
    arguments: list[str]


def _normalize_arguments(arguments: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for argument in arguments:
        value = str(argument).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _humanize_name(name: str) -> str:
    parts = [part for part in re.split(r"[_\-\s]+", name.strip()) if part]
    return " ".join(part.capitalize() for part in parts) or "Prompt"


def _heuristic_polish(draft: PromptDraft) -> PromptDraft:
    normalized_args = _normalize_arguments(draft.arguments)
    title = draft.title.strip() or _humanize_name(draft.name)
    description = draft.description.strip() or (
        f"Guide the model to act as {title.lower()} with grounded, actionable output."
    )
    base_task = draft.content_template.strip()
    arg_section = "\n".join(f"- {{{argument}}}" for argument in normalized_args)
    if not arg_section:
        arg_section = "- No named placeholders required."

    polished_template = "\n\n".join(
        section
        for section in [
            f"## Role\nYou are {title}. {description}",
            f"## Inputs\n{arg_section}",
            (
                "## Task\n" + base_task
                if base_task
                else "## Task\nRespond with a concrete, well-structured answer tailored to the provided inputs."
            ),
            "## Output Requirements\n- Be specific and practical.\n- Preserve important technical constraints.\n- Avoid filler and generic advice.",
        ]
        if section.strip()
    )

    return PromptDraft(
        name=draft.name.strip(),
        title=title,
        description=description,
        content_template=polished_template,
        arguments=normalized_args,
    )


def _extract_json_object(raw: str) -> dict[str, object] | None:
    if not raw.strip():
        return None
    candidates = re.findall(r"\{.*\}", raw, flags=re.DOTALL)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def polish_prompt_draft(
    draft: PromptDraft, config: MinderConfig
) -> tuple[PromptDraft, dict[str, str]]:
    from minder.llm.factory import create_llm

    polished = _heuristic_polish(draft)
    llm = create_llm(config.llm)
    runtime = llm.runtime

    instruction = """You are polishing an MCP prompt template for an engineering assistant.
Return only valid JSON with keys: title, description, content_template.
Keep placeholders exactly as provided, for example {repo_name} or {error}.
Do not invent new placeholders.
Make the prompt direct, structured, and useful for a coding workflow.
"""
    request_payload = {
        "name": polished.name,
        "title": polished.title,
        "description": polished.description,
        "arguments": polished.arguments,
        "content_template": polished.content_template,
    }
    llm_response = llm.complete_text(
        f"{instruction}\n\nDraft:\n{json.dumps(request_payload, ensure_ascii=True, indent=2)}",
        max_tokens=900,
        temperature=min(max(config.llm.temperature, 0.05), 0.3),
        fallback="",
    )
    parsed = _extract_json_object(llm_response)
    if not parsed:
        return polished, {
            "provider": "heuristic",
            "model": config.llm.provider,
            "runtime": runtime,
        }

    merged = PromptDraft(
        name=polished.name,
        title=str(parsed.get("title", polished.title)).strip() or polished.title,
        description=(
            str(parsed.get("description", polished.description)).strip()
            or polished.description
        ),
        content_template=(
            str(parsed.get("content_template", polished.content_template)).strip()
            or polished.content_template
        ),
        arguments=polished.arguments,
    )
    return merged, {
        "provider": "local_llm",
        "model": config.llm.provider,
        "runtime": runtime,
    }
