"""MCP prompt registration and runtime sync for Minder."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Iterable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import Prompt, PromptArgument

if TYPE_CHECKING:
    from minder.store.interfaces import IOperationalStore


class PromptRegistry:
    """Registers all Minder MCP prompts onto a :class:`FastMCP` app."""

    _BUILTIN_NAMES = {"debug", "review", "explain", "tdd_step", "query_reasoning"}
    _BUILTIN_DEFINITIONS: dict[str, dict[str, Any]] = {
        "debug": {
            "title": "Debug Assistant",
            "description": (
                "Structured prompt to diagnose errors with root cause analysis, "
                "ranked hypotheses, and a minimal fix proposal."
            ),
            "arguments": ["error", "context"],
            "defaults": {
                "error": "Paste the error message or stack trace here.",
                "context": "",
            },
            "content_template": "\n\n".join(
                [
                    "## Error\n```\n{error}\n```",
                    "## Context\n{context}",
                    "## Task",
                    "1. Identify the root cause of the error above.",
                    "2. List 2-3 hypotheses ranked by likelihood.",
                    "3. Propose the minimal fix with a code snippet.",
                    "4. Describe how to verify the fix.",
                ]
            ),
        },
        "review": {
            "title": "Code Reviewer",
            "description": (
                "Code review checklist prompt for structured diff analysis covering "
                "correctness, edge cases, tests, performance, security, and readability."
            ),
            "arguments": ["diff", "context"],
            "defaults": {
                "diff": "Paste the diff or changed code here.",
                "context": "",
            },
            "content_template": "\n\n".join(
                [
                    "## Diff\n```diff\n{diff}\n```",
                    "## Context\n{context}",
                    "## Review Checklist",
                    "- [ ] **Correctness** — Does the logic match the stated intent?",
                    "- [ ] **Edge cases** — Are failure modes and null/empty states handled?",
                    "- [ ] **Tests** — Are new behaviours covered by automated tests?",
                    "- [ ] **Performance** — Any N+1 queries, unbounded loops, or hot-path regressions?",
                    "- [ ] **Security** — Any injection vectors, auth bypass, or data leakage?",
                    "- [ ] **Readability** — Is naming clear and are comments useful?",
                    "",
                    "Provide **BLOCKING** issues first, then **RECOMMENDED** improvements, then **SUGGESTIONS**.",
                ]
            ),
        },
        "explain": {
            "title": "Code Explainer",
            "description": (
                "Explain a code snippet in plain language with a summary, "
                "step-by-step walkthrough, gotchas, and a usage example."
            ),
            "arguments": ["code", "language"],
            "defaults": {
                "code": "Paste the code snippet here.",
                "language": "python",
            },
            "content_template": "\n\n".join(
                [
                    "## Code ({language})\n```{language}\n{code}\n```",
                    "## Task",
                    "Explain the code above clearly:",
                    "1. **What it does** — one-sentence summary.",
                    "2. **How it works** — step-by-step walkthrough of the key logic.",
                    "3. **Gotchas** — any non-obvious behaviour, edge cases, or side effects.",
                    "4. **Example** — show a concrete usage example if helpful.",
                ]
            ),
        },
        "tdd_step": {
            "title": "TDD Step Guide",
            "description": (
                "Workflow-aware TDD guidance tailored to the current step "
                "(Test Writing, Implementation, or Review)."
            ),
            "arguments": ["current_step", "failing_tests"],
            "defaults": {
                "current_step": "Test Writing",
                "failing_tests": "",
            },
            "content_template": "\n\n".join(
                [
                    "## Current Workflow Step: {current_step}",
                    "## Failing Tests\n```\n{failing_tests}\n```",
                    "## Guidance",
                    "Tailor the response to the workflow step above and keep the next action concrete.",
                ]
            ),
        },
        "query_reasoning": {
            "title": "Query Reasoning",
            "description": (
                "Primary query reasoning prompt that injects workflow instruction, "
                "continuity packet, retrieved context, and corrective retry guidance."
            ),
            "arguments": [
                "workflow_instruction",
                "instruction_envelope",
                "continuity_brief",
                "continuity_packet",
                "user_query",
                "retrieved_context",
                "correction_required",
            ],
            "defaults": {
                "workflow_instruction": "",
                "instruction_envelope": "{}",
                "continuity_brief": "{}",
                "continuity_packet": "{}",
                "user_query": "Summarize the current repository state.",
                "retrieved_context": "No repository context found.",
                "correction_required": "",
            },
            "content_template": "\n\n".join(
                [
                    "Workflow instruction:\n{workflow_instruction}",
                    "Instruction envelope:\n{instruction_envelope}",
                    "Continuity packet:\n{continuity_packet}",
                    "User query:\n{user_query}",
                    "Retrieved context:\n{retrieved_context}",
                    "Correction required:\n{correction_required}",
                    "Respond with grounded reasoning and cite source paths.",
                ]
            ),
        },
    }

    @staticmethod
    def get_builtin_definition(name: str) -> dict[str, Any] | None:
        definition = PromptRegistry._BUILTIN_DEFINITIONS.get(name)
        if definition is None:
            return None
        return {
            "title": definition["title"],
            "description": definition["description"],
            "arguments": list(definition["arguments"]),
            "defaults": dict(definition.get("defaults", {})),
            "content_template": str(definition["content_template"]),
        }

    @staticmethod
    def get_builtin_prompt_model(name: str) -> SimpleNamespace | None:
        definition = PromptRegistry.get_builtin_definition(name)
        if definition is None:
            return None
        return SimpleNamespace(
            id=f"builtin:{name}",
            name=name,
            title=definition["title"],
            description=definition["description"],
            content_template=definition["content_template"],
            arguments=list(definition["arguments"]),
            defaults=dict(definition.get("defaults", {})),
            created_at=None,
            updated_at=None,
            is_builtin=True,
        )

    @staticmethod
    async def resolve_prompt_model(
        name: str,
        store: IOperationalStore | None = None,
    ) -> Any | None:
        if store is not None:
            prompt = await store.get_prompt_by_name(name)
            if prompt is not None:
                return prompt
        return PromptRegistry.get_builtin_prompt_model(name)

    @staticmethod
    def render_content_template(
        content_template: str,
        arguments: dict[str, Any],
        *,
        defaults: dict[str, Any] | None = None,
    ) -> str:
        rendered = str(content_template)
        merged_arguments = dict(defaults or {})
        merged_arguments.update(arguments)
        for arg_name, arg_val in merged_arguments.items():
            rendered = rendered.replace("{" + str(arg_name) + "}", str(arg_val or ""))
        return rendered

    @staticmethod
    def _prompt_manager(app: FastMCP) -> Any:
        return getattr(app, "_prompt_manager")

    @staticmethod
    def _upsert_prompt(app: FastMCP, prompt: Prompt) -> None:
        manager = PromptRegistry._prompt_manager(app)
        existing = manager._prompts.get(prompt.name)
        if existing is None:
            app.add_prompt(prompt)
            return
        existing.title = prompt.title
        existing.description = prompt.description
        existing.arguments = prompt.arguments
        existing.fn = prompt.fn
        existing.context_kwarg = prompt.context_kwarg

    @staticmethod
    def _remove_prompt(app: FastMCP, name: str) -> None:
        manager = PromptRegistry._prompt_manager(app)
        manager._prompts.pop(name, None)

    @staticmethod
    def _optional_arguments(name: str) -> list[PromptArgument]:
        definition = PromptRegistry._BUILTIN_DEFINITIONS[name]
        return [
            PromptArgument(name=argument_name, required=False)
            for argument_name in definition["arguments"]
        ]

    @staticmethod
    def _configure_builtin_prompt(prompt: Prompt) -> Prompt:
        prompt.arguments = PromptRegistry._optional_arguments(prompt.name)
        return prompt

    @staticmethod
    def builtin_prompt_models() -> list[SimpleNamespace]:
        return [
            PromptRegistry.get_builtin_prompt_model(name)
            for name in PromptRegistry._BUILTIN_DEFINITIONS
            if PromptRegistry.get_builtin_prompt_model(name) is not None
        ]

    @staticmethod
    def _normalize_argument_names(raw_arguments: Any) -> list[str]:
        if raw_arguments is None:
            return []
        if isinstance(raw_arguments, dict):
            candidates: Iterable[Any] = raw_arguments.keys()
        elif isinstance(raw_arguments, (list, tuple, set)):
            candidates = raw_arguments
        else:
            candidates = [raw_arguments]

        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            value = item.get("name") if isinstance(item, dict) else item
            argument = str(value or "").strip()
            if not argument or argument in seen:
                continue
            seen.add(argument)
            normalized.append(argument)
        return normalized

    @staticmethod
    def _build_dynamic_handler(prompt_model: Any, store: IOperationalStore):
        async def dynamic_handler(**kwargs):
            from minder.auth.context import get_current_principal

            principal = get_current_principal()
            actor_id = str(principal.principal_id) if principal else "unknown"
            actor_type = principal.principal_type if principal else "unknown"
            client_id = (
                getattr(principal, "client_slug", "unknown") if principal else "unknown"
            )

            try:
                await store.create_audit_log(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_type="prompt_request",
                    resource_type="prompt",
                    resource_id=prompt_model.name,
                    outcome="success",
                    audit_metadata={"client_id": client_id},
                )
            except Exception:
                pass

            content = PromptRegistry.render_content_template(
                str(prompt_model.content_template),
                kwargs,
                defaults=dict(getattr(prompt_model, "defaults", {}) or {}),
            )
            return [{"role": "user", "content": content}]

        dynamic_handler.__name__ = f"prompt_{prompt_model.name}"
        return dynamic_handler

    @staticmethod
    def register(app: FastMCP, store: IOperationalStore | None = None) -> None:
        """Register builtin prompts using a mutable runtime registry."""

        debug_defaults = PromptRegistry._BUILTIN_DEFINITIONS["debug"]["defaults"]
        review_defaults = PromptRegistry._BUILTIN_DEFINITIONS["review"]["defaults"]
        explain_defaults = PromptRegistry._BUILTIN_DEFINITIONS["explain"]["defaults"]
        tdd_step_defaults = PromptRegistry._BUILTIN_DEFINITIONS["tdd_step"]["defaults"]
        query_reasoning_defaults = PromptRegistry._BUILTIN_DEFINITIONS[
            "query_reasoning"
        ]["defaults"]

        async def _log_prompt(name: str):
            if store is not None:
                from minder.auth.context import get_current_principal

                p = get_current_principal()
                actor_id = "unknown"
                actor_type = "unknown"
                client_id = "unknown"
                if p:
                    actor_id = str(p.principal_id)
                    actor_type = p.principal_type
                    client_id = getattr(p, "client_slug", "unknown")

                try:
                    await store.create_audit_log(
                        actor_type=actor_type,
                        actor_id=actor_id,
                        event_type="prompt_request",
                        resource_type="prompt",
                        resource_id=name,
                        outcome="success",
                        audit_metadata={"client_id": client_id},
                    )
                except Exception:
                    pass

        async def debug_prompt(
            error: str = str(debug_defaults["error"]),
            context: str = str(debug_defaults["context"]),
        ) -> list[dict[str, str]]:
            await _log_prompt("debug")
            """Generate a debug analysis prompt.

            Args:
                error:   The error message or stack trace to diagnose.
                context: Optional surrounding context (file, function, recent changes).
            """
            parts = [f"## Error\n```\n{error}\n```"]
            if context:
                parts.append(f"## Context\n{context}")
            parts += [
                "## Task",
                "1. Identify the root cause of the error above.",
                "2. List 2-3 hypotheses ranked by likelihood.",
                "3. Propose the minimal fix with a code snippet.",
                "4. Describe how to verify the fix.",
            ]
            return [{"role": "user", "content": "\n\n".join(parts)}]

        async def review_prompt(
            diff: str = str(review_defaults["diff"]),
            context: str = str(review_defaults["context"]),
        ) -> list[dict[str, str]]:
            await _log_prompt("review")
            """Generate a code review prompt.

            Args:
                diff:    The unified diff or changed code to review.
                context: Optional ticket description, requirements, or intent.
            """
            parts = [f"## Diff\n```diff\n{diff}\n```"]
            if context:
                parts.append(f"## Context\n{context}")
            parts += [
                "## Review Checklist",
                "- [ ] **Correctness** — Does the logic match the stated intent?",
                "- [ ] **Edge cases** — Are failure modes and null/empty states handled?",
                "- [ ] **Tests** — Are new behaviours covered by automated tests?",
                "- [ ] **Performance** — Any N+1 queries, unbounded loops, or hot-path regressions?",
                "- [ ] **Security** — Any injection vectors, auth bypass, or data leakage?",
                "- [ ] **Readability** — Is naming clear and are comments useful?",
                "",
                "Provide **BLOCKING** issues first, then **RECOMMENDED** improvements, "
                "then **SUGGESTIONS**.",
            ]
            return [{"role": "user", "content": "\n\n".join(parts)}]

        async def explain_prompt(
            code: str = str(explain_defaults["code"]),
            language: str = str(explain_defaults["language"]),
        ) -> list[dict[str, str]]:
            await _log_prompt("explain")
            """Generate a code explanation prompt.

            Args:
                code:     The source code snippet to explain.
                language: The programming language (default: python).
            """
            content = "\n\n".join(
                [
                    f"## Code ({language})\n```{language}\n{code}\n```",
                    "## Task",
                    "Explain the code above clearly:",
                    "1. **What it does** — one-sentence summary.",
                    "2. **How it works** — step-by-step walkthrough of the key logic.",
                    "3. **Gotchas** — any non-obvious behaviour, edge cases, or side effects.",
                    "4. **Example** — show a concrete usage example if helpful.",
                ]
            )
            return [{"role": "user", "content": content}]

        async def tdd_step_prompt(
            current_step: str = str(tdd_step_defaults["current_step"]),
            failing_tests: str = str(tdd_step_defaults["failing_tests"]),
        ) -> list[dict[str, str]]:
            await _log_prompt("tdd_step")
            """Generate a TDD step guidance prompt.

            Args:
                current_step:  The name of the current workflow step.
                failing_tests: Optional failing test output to include as context.
            """
            parts = [f"## Current Workflow Step: {current_step}"]
            if failing_tests:
                parts.append(f"## Failing Tests\n```\n{failing_tests}\n```")

            lowered = current_step.lower()
            if "test" in lowered:
                parts += [
                    "## Guidance",
                    "You are in the **Test Writing** phase.",
                    "1. Write failing tests that specify the exact behaviour required.",
                    "2. Do NOT write any implementation code yet.",
                    "3. Each test should express a single, clear assertion.",
                    "4. Name tests descriptively: `test_<behaviour>_when_<condition>`.",
                ]
            elif "implement" in lowered:
                parts += [
                    "## Guidance",
                    "You are in the **Implementation** phase.",
                    "1. Write the minimal code to make all failing tests pass.",
                    "2. Do not add features beyond what the tests require.",
                    "3. Run tests after every small change.",
                    "4. Refactor only after all tests are green.",
                ]
            elif "review" in lowered:
                parts += [
                    "## Guidance",
                    "You are in the **Review** phase.",
                    "1. Verify that all acceptance criteria are met.",
                    "2. Confirm no regressions exist in the existing test suite.",
                    "3. Ensure code quality meets project standards.",
                ]
            else:
                parts += [
                    "## Guidance",
                    f"Complete **{current_step}** fully before advancing to the next step.",
                    "Do not skip or partially satisfy prerequisites.",
                ]

            return [{"role": "user", "content": "\n\n".join(parts)}]

        async def query_reasoning_prompt(
            workflow_instruction: str = str(
                query_reasoning_defaults["workflow_instruction"]
            ),
            instruction_envelope: str = str(
                query_reasoning_defaults["instruction_envelope"]
            ),
            continuity_brief: str = str(query_reasoning_defaults["continuity_brief"]),
            continuity_packet: str = str(query_reasoning_defaults["continuity_packet"]),
            user_query: str = str(query_reasoning_defaults["user_query"]),
            retrieved_context: str = str(query_reasoning_defaults["retrieved_context"]),
            correction_required: str = str(
                query_reasoning_defaults["correction_required"]
            ),
        ) -> list[dict[str, str]]:
            await _log_prompt("query_reasoning")
            content = PromptRegistry.render_content_template(
                str(
                    PromptRegistry._BUILTIN_DEFINITIONS["query_reasoning"][
                        "content_template"
                    ]
                ),
                {
                    "workflow_instruction": workflow_instruction,
                    "instruction_envelope": instruction_envelope,
                    "continuity_brief": continuity_brief,
                    "continuity_packet": continuity_packet,
                    "user_query": user_query,
                    "retrieved_context": retrieved_context,
                    "correction_required": correction_required,
                },
                defaults=query_reasoning_defaults,
            )
            return [{"role": "user", "content": content}]

        PromptRegistry._upsert_prompt(
            app,
            PromptRegistry._configure_builtin_prompt(
                Prompt.from_function(
                    debug_prompt,
                    name="debug",
                    title=PromptRegistry._BUILTIN_DEFINITIONS["debug"]["title"],
                    description=PromptRegistry._BUILTIN_DEFINITIONS["debug"][
                        "description"
                    ],
                )
            ),
        )
        PromptRegistry._upsert_prompt(
            app,
            PromptRegistry._configure_builtin_prompt(
                Prompt.from_function(
                    review_prompt,
                    name="review",
                    title=PromptRegistry._BUILTIN_DEFINITIONS["review"]["title"],
                    description=PromptRegistry._BUILTIN_DEFINITIONS["review"][
                        "description"
                    ],
                )
            ),
        )
        PromptRegistry._upsert_prompt(
            app,
            PromptRegistry._configure_builtin_prompt(
                Prompt.from_function(
                    explain_prompt,
                    name="explain",
                    title=PromptRegistry._BUILTIN_DEFINITIONS["explain"]["title"],
                    description=PromptRegistry._BUILTIN_DEFINITIONS["explain"][
                        "description"
                    ],
                )
            ),
        )
        PromptRegistry._upsert_prompt(
            app,
            PromptRegistry._configure_builtin_prompt(
                Prompt.from_function(
                    tdd_step_prompt,
                    name="tdd_step",
                    title=PromptRegistry._BUILTIN_DEFINITIONS["tdd_step"]["title"],
                    description=PromptRegistry._BUILTIN_DEFINITIONS["tdd_step"][
                        "description"
                    ],
                )
            ),
        )
        PromptRegistry._upsert_prompt(
            app,
            PromptRegistry._configure_builtin_prompt(
                Prompt.from_function(
                    query_reasoning_prompt,
                    name="query_reasoning",
                    title=PromptRegistry._BUILTIN_DEFINITIONS["query_reasoning"][
                        "title"
                    ],
                    description=PromptRegistry._BUILTIN_DEFINITIONS["query_reasoning"][
                        "description"
                    ],
                )
            ),
        )

    @staticmethod
    async def sync(app: FastMCP, store: IOperationalStore) -> None:
        """Synchronize FastMCP prompts with builtin and database-backed prompt data."""
        PromptRegistry.register(app, store=store)
        try:
            prompts = await store.list_prompts()
        except Exception:
            return

        dynamic_names: set[str] = set()
        for prompt_model in prompts:
            argument_names = PromptRegistry._normalize_argument_names(
                getattr(prompt_model, "arguments", None)
            )
            dynamic_handler = PromptRegistry._build_dynamic_handler(prompt_model, store)

            dynamic_prompt = Prompt.from_function(
                dynamic_handler,
                name=str(prompt_model.name),
                title=str(prompt_model.title),
                description=str(prompt_model.description),
            )
            dynamic_prompt.arguments = [
                PromptArgument(name=name, required=False) for name in argument_names
            ]
            PromptRegistry._upsert_prompt(app, dynamic_prompt)
            dynamic_names.add(str(prompt_model.name))

        previous_dynamic_names = set(
            getattr(app, "_minder_dynamic_prompt_names", set())
        )
        for stale_name in previous_dynamic_names - dynamic_names:
            if stale_name not in PromptRegistry._BUILTIN_NAMES:
                PromptRegistry._remove_prompt(app, stale_name)

        setattr(app, "_minder_dynamic_prompt_names", dynamic_names)
