"""
Domain Value Objects — single source of truth for tool names, descriptions, and scope metadata.
Moved to the Domain layer to prevent Presentation (tools/) dependencies from leaking into Application layers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolMeta:
    name: str
    description: str
    scopeable: bool = True
    """Whether this tool can be granted to client principals via tool_scopes."""
    always_available: bool = False
    """If True, ClientPrincipal can call this tool regardless of their tool_scopes grant list."""


# All registered MCP tools — ordered for display
ALL_TOOLS: list[ToolMeta] = [
    # ── Memory ────────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_memory_store",
        description=(
            "Create or update a project-specific memory entry. "
            "Pass memory_id to update an existing entry; omit to create new. "
            "Use for facts specific to this project — not reusable patterns (use minder_skill_store for those)."
        ),
    ),
    ToolMeta(
        name="minder_memory_recall",
        description=(
            "Search stored memory entries by semantic similarity. "
            "Call before starting work that may depend on past decisions, constraints, or project-specific context. "
            "Prefer over minder_skill_recall when seeking project facts rather than reusable patterns."
        ),
    ),
    ToolMeta(
        name="minder_memory_list",
        description=(
            "List all stored memory entry IDs and titles. "
            "Use to audit what has been saved — not for retrieval (use minder_memory_recall for that)."
        ),
    ),
    ToolMeta(
        name="minder_memory_delete",
        description="Delete a stored memory entry by its ID. Only call when explicitly asked to remove a specific memory.",
    ),
    # ── Skills ────────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_skill_store",
        description=(
            "Create or update a reusable skill (workflow pattern, checklist, code convention). "
            "Pass skill_id to update an existing skill; omit to create new. Pass deprecated=True to retire a skill. "
            "Use for cross-project reusable knowledge — not project-specific facts (use minder_memory_store for those)."
        ),
    ),
    ToolMeta(
        name="minder_skill_recall",
        description=(
            "Retrieve reusable skills ranked by workflow-step compatibility and semantic relevance. "
            "Call at the start of each workflow step to load applicable patterns and conventions before acting. "
            "Pass current_step to get step-specific skills first."
        ),
    ),
    ToolMeta(
        name="minder_skill_list",
        description=(
            "List stored skills with optional workflow-step, tag, and quality filters. "
            "Use to audit available skills — not for retrieval (use minder_skill_recall for that)."
        ),
    ),
    ToolMeta(
        name="minder_skill_delete",
        description="Delete a stored skill by its ID. Only call when explicitly asked to remove a skill.",
    ),
    # ── Search & Query ────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_search_code",
        description=(
            "Search indexed repository source files for relevant code by semantic query. "
            "Use for content-level questions: 'where is X implemented', 'files that handle Y'. "
            "Requires repo_path. Prefer minder_search_graph for structural/relational queries."
        ),
    ),
    ToolMeta(
        name="minder_search_errors",
        description=(
            "Search indexed errors and troubleshooting history for relevant matches. "
            "Call when investigating a failure or looking for prior resolutions. Does not require repo_path."
        ),
    ),
    ToolMeta(
        name="minder_find_impact",
        description=(
            "Traverse the repository graph to show upstream and downstream impact for a file, symbol, route, or dependency. "
            "Call before making changes to assess blast radius. Requires repo_path."
        ),
    ),
    ToolMeta(
        name="minder_search_graph",
        description=(
            "Search the repository graph for files, symbols, routes, todos, or dependencies by query. "
            "Use for structural/relational questions: 'which routes call X', 'what depends on Y'. "
            "Requires repo_path. Prefer over minder_search_code for graph-navigable entities."
        ),
    ),
    # ── Workflow ──────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_workflow_step",
        description=(
            "Return the current workflow step, progress, and instruction envelope for a repository. "
            "Pass include_definition=true to also get the full workflow definition (steps, policies). "
            "Also used to submit an approval decision when resuming an interrupted workflow."
        ),
    ),
    ToolMeta(
        name="minder_workflow_update",
        description=(
            "Mark a workflow step complete and persist a required artifact. "
            "Call after completing all required artifacts for the current step to advance the workflow."
        ),
    ),
    ToolMeta(
        name="minder_workflow_guard",
        description=(
            "Validate that a requested workflow step transition is currently permitted. "
            "ALWAYS call before starting or switching to a new step. Never skip this check."
        ),
    ),
    # ── Session ───────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_session_boot",
        description=(
            "MANDATORY FIRST CALL at every session start. "
            "Find-or-create a session in one call. Pass session_id to restore a known session by UUID. "
            "Returns session_id, session_found, prior state, session_summary, and _next_steps. "
            "Pass project_context with repo_path to seed location even before repo_id is resolved. "
            "Idempotent: safe to call even if a session already exists."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_list",
        description=(
            "List all sessions owned by this principal (newest first). "
            "Use only when you do not know the session name — prefer minder_session_boot when you know the name."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_save",
        description=(
            "Checkpoint the current task state. Pass branch and open_files to also update context. "
            "Call after each significant wave of work (decisions made, files changed, next steps planned). "
            "Do not wait until end of session — checkpoint frequently."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_summarize",
        description=(
            "Generate and persist a structured work summary for the session (task, steps completed, blockers, next actions). "
            "Call before /compact, before long gaps, or when the conversation grows long. "
            "This summary is recovered by minder_session_boot on the next session."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_cleanup",
        description=(
            "Delete expired sessions and remove their history records. "
            "Only call when the user explicitly asks to clean up old sessions."
        ),
        always_available=True,
    ),
    # ── Auth (internal — not grantable to client principals) ─────────────────
    ToolMeta(
        name="minder_auth_login",
        description="Exchange an admin API key for a JWT bearer token. One-time auth step — do not call repeatedly.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_exchange_client_key",
        description="Exchange a client API key for a scoped access token. One-time auth step.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_whoami",
        description=(
            "Return the current principal's identity, role, and granted scopes. "
            "Call only when you need to inspect available permissions explicitly."
        ),
        scopeable=False,
        always_available=True,
    ),
    # ── SubAgents ─────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_agent_list",
        description=(
            "List available SubAgent definitions (name, title, description, workflow steps — no system_prompt). "
            "Call before delegating work to discover which agents are available for a given workflow step."
        ),
        scopeable=True,
        always_available=True,
    ),
    ToolMeta(
        name="minder_agent_get",
        description=(
            "Get the full SubAgent definition by name, including system_prompt and tools list. "
            "Call after minder_agent_list to load the full prompt before spawning an agent."
        ),
        scopeable=True,
        always_available=True,
    ),
    ToolMeta(
        name="minder_agent_store",
        description=(
            "Create or update (upsert) a SubAgent definition by name. "
            "All fields are required on create; on update, omit unchanged fields."
        ),
        scopeable=True,
    ),
]

# Flat dict for fast lookup by name (used in bootstrap/transport.py)
TOOL_DESCRIPTIONS: dict[str, str] = {tool.name: tool.description for tool in ALL_TOOLS}

# Tools that can be granted to client principals
SCOPEABLE_TOOLS: list[ToolMeta] = [tool for tool in ALL_TOOLS if tool.scopeable]

# Tools always callable by any authenticated ClientPrincipal (no scope grant required)
ALWAYS_AVAILABLE_FOR_CLIENTS: frozenset[str] = frozenset(
    tool.name for tool in ALL_TOOLS if tool.always_available
)

# Default tool_scopes for new agent clients — all scopeable tools.
DEFAULT_AGENT_TOOL_SCOPES: frozenset[str] = frozenset(
    tool.name for tool in SCOPEABLE_TOOLS
)


TOOL_USAGE_PATTERNS: dict[str, str] = {
    # ── Session lifecycle ──────────────────────────────────────────────────────
    "minder_session_boot": (
        "CALL FIRST at every session start. Pass project_name (stable slug) and project_context with repo_path. "
        "Cache session_id immediately. If session_found=true, read session_summary for orientation. "
        "Pass session_id to restore a specific session by UUID. Follow _next_steps in the response."
    ),
    "minder_session_save": (
        "Call after EACH significant wave of work: after decisions, after changing files, after completing a step. "
        "Pass branch and open_files when switching context to keep session state accurate. "
        "Do not wait until end of session — checkpoint frequently."
    ),
    "minder_session_summarize": (
        "Call proactively when the conversation exceeds ~20 exchanges, before any /compact, "
        "or before a long interruption. This summary is recovered on next session start via minder_session_boot."
    ),
    "minder_session_cleanup": (
        "Only call when the user explicitly asks to purge old sessions. "
        "Never call proactively during normal work."
    ),
    # ── Workflow ───────────────────────────────────────────────────────────────
    "minder_workflow_guard": (
        "MANDATORY before starting or switching to ANY workflow step. "
        "If guard returns allowed=false, do not proceed — surface the blocking reason to the user."
    ),
    "minder_workflow_step": (
        "Call to get current workflow position and instruction_envelope. "
        "Pass include_definition=true once at session start to get the full workflow definition. "
        "Cache current_step and use it in skill_recall and memory_recall."
    ),
    "minder_workflow_update": (
        "Call after completing ALL required artifacts for the current step to advance the workflow. "
        "Do not call unless the step is truly complete — partial completion should be saved via minder_session_save instead."
    ),
    # ── Memory ────────────────────────────────────────────────────────────────
    "minder_memory_recall": (
        "Call before answering questions that depend on past project decisions or constraints. "
        "Use current_step to bias results toward step-relevant memories. "
        "Do not call for general code patterns — use minder_skill_recall instead."
    ),
    "minder_memory_store": (
        "Call when the user states a project-specific fact, decision, or constraint that should persist. "
        "Pass memory_id to update an existing entry. "
        "Do not use for reusable patterns or conventions — use minder_skill_store for those."
    ),
    # ── Skills ────────────────────────────────────────────────────────────────
    "minder_skill_recall": (
        "Call at the START of each workflow step to load applicable patterns, checklists, and conventions. "
        "Always pass current_step so step-compatible skills rank first. "
        "Do not use for project-specific facts — use minder_memory_recall for those."
    ),
    "minder_skill_store": (
        "Call when a reusable workflow pattern, checklist, code template, or convention is identified. "
        "Pass skill_id to update an existing skill; pass deprecated=True to retire it. "
        "Must be applicable across projects — project-specific knowledge belongs in minder_memory_store."
    ),
    # ── Code search ───────────────────────────────────────────────────────────
    "minder_search_code": (
        "Use for content-level lookup: 'where is X implemented', 'files that handle Y'. "
        "Requires repo_path. For structural queries (routes, symbols, dependencies), prefer minder_search_graph."
    ),
    "minder_search_graph": (
        "Use for structural/relational queries: 'which routes call X', 'what imports Y', 'show me dependencies'. "
        "More precise than minder_search_code for graph-navigable entities."
    ),
    "minder_find_impact": (
        "Call before making changes to assess blast radius. "
        "Pass the file, symbol, or route being changed. "
        "Review upstream and downstream impact before proceeding."
    ),
    "minder_search_errors": (
        "Call when investigating a failure or looking for prior resolutions. "
        "Does not require repo_path — searches across all indexed errors."
    ),
    # ── SubAgents ─────────────────────────────────────────────────────────────
    "minder_agent_list": (
        "Call at the start of a step that benefits from delegation (review, testing, analysis). "
        "Filter by workflow_step to find agents scoped to the current step."
    ),
    "minder_agent_get": (
        "Call after minder_agent_list to load the full system_prompt and tool list "
        "before spawning the agent. Do not spawn without reading the prompt first."
    ),
}


def _tool_category(tool_name: str) -> str:
    if tool_name.startswith("minder_memory_"):
        return "Memory"
    if tool_name.startswith("minder_skill_"):
        return "Skills"
    if tool_name.startswith("minder_search_") or tool_name == "minder_find_impact":
        return "Search and query"
    if tool_name.startswith("minder_workflow_"):
        return "Workflow"
    if tool_name.startswith("minder_session_"):
        return "Sessions"
    if tool_name.startswith("minder_auth_"):
        return "Auth and identity"
    if tool_name.startswith("minder_agent_"):
        return "SubAgents"
    return "Other"


def tool_capability_manifest() -> str:
    grouped: dict[str, list[ToolMeta]] = {}
    for tool in ALL_TOOLS:
        grouped.setdefault(_tool_category(tool.name), []).append(tool)

    ordered_categories = [
        "Sessions",
        "Workflow",
        "Memory",
        "Skills",
        "Search and query",
        "SubAgents",
        "Auth and identity",
        "Other",
    ]
    lines = [
        "STARTUP: minder_session_boot(project_name, project_context) → PARALLEL [minder_workflow_step + minder_skill_recall] → minder_memory_recall.",
        "Repo-scoped tools (search_code, search_graph, find_impact, workflow_*) require repo_path or repo_id.",
        "Read minder://instructions for the complete sequencing guide before calling any tools.",
        "Every tool response includes _next_steps — read and follow these hints.",
    ]
    for category in ordered_categories:
        tools = grouped.get(category, [])
        if not tools:
            continue
        lines.append(f"\n{category}:")
        for tool in tools:
            availability = (
                "always available"
                if tool.always_available
                else "scoped" if tool.scopeable else "admin/internal"
            )
            lines.append(f"  {tool.name} [{availability}]: {tool.description}")
    lines.append("\nKey sequencing rules:")
    for tool_name, pattern in TOOL_USAGE_PATTERNS.items():
        lines.append(f"  {tool_name}: {pattern}")
    return "\n".join(lines)


def tool_data_access_policy() -> str:
    return "\n".join(
        [
            "Minder may read and update its own operational data where matching tools exist, including memories, skills, workflow state, sessions, client credentials, and repository metadata.",
            "User account records are read-only. Minder may inspect identity information through read-only auth tools such as whoami, but it must not claim it can create, edit, rotate, deactivate, or delete users.",
            "Repository-aware search, graph traversal, and query actions require repository context before they can inspect code or graph state.",
            "If a request asks what Minder can do, answer from the tool capability manifest instead of saying no tools are available.",
        ]
    )
