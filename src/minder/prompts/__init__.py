"""
MCP Prompt registration for Minder.

Provides four prompt templates that MCP clients can invoke to receive
structured guidance messages:

``debug``
    Structured root-cause-analysis prompt for diagnosing errors.

``review``
    Code review checklist prompt for structured diff analysis.

``explain``
    Plain-language explanation of a code snippet.

``tdd_step``
    Workflow-aware TDD guidance for the current step.
"""

from mcp.server.fastmcp import FastMCP
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from minder.store.interfaces import IOperationalStore

class PromptRegistry:
    """Registers all Minder MCP prompts onto a :class:`FastMCP` app."""

    @staticmethod
    def register(app: FastMCP, store: IOperationalStore | None = None) -> None:
        """Register ``debug``, ``review``, ``explain``, and ``tdd_step`` prompts.

        Args:
            app: The FastMCP application to register prompts with.
            store: Optional operational store for audit logging.
        """

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
                        audit_metadata={"client_id": client_id}
                    )
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # debug — root cause analysis
        # ------------------------------------------------------------------

        @app.prompt(
            name="debug",
            title="Debug Assistant",
            description=(
                "Structured prompt to diagnose errors with root cause analysis, "
                "ranked hypotheses, and a minimal fix proposal."
            ),
        )
        async def debug_prompt(
            error: str,
            context: str = "",
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

        # ------------------------------------------------------------------
        # review — code review checklist
        # ------------------------------------------------------------------

        @app.prompt(
            name="review",
            title="Code Reviewer",
            description=(
                "Code review checklist prompt for structured diff analysis covering "
                "correctness, edge cases, tests, performance, security, and readability."
            ),
        )
        async def review_prompt(
            diff: str,
            context: str = "",
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

        # ------------------------------------------------------------------
        # explain — code explanation
        # ------------------------------------------------------------------

        @app.prompt(
            name="explain",
            title="Code Explainer",
            description=(
                "Explain a code snippet in plain language with a summary, "
                "step-by-step walkthrough, gotchas, and a usage example."
            ),
        )
        async def explain_prompt(
            code: str,
            language: str = "python",
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

        # ------------------------------------------------------------------
        # tdd_step — workflow-aware TDD guidance
        # ------------------------------------------------------------------

        @app.prompt(
            name="tdd_step",
            title="TDD Step Guide",
            description=(
                "Workflow-aware TDD guidance tailored to the current step "
                "(Test Writing, Implementation, or Review)."
            ),
        )
        async def tdd_step_prompt(
            current_step: str,
            failing_tests: str = "",
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
