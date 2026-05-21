"""
Tool Registry — single source of truth for tool names, descriptions, and scope metadata.

Import TOOL_DESCRIPTIONS in bootstrap/transport.py to register tools.
Import SCOPEABLE_TOOLS in admin use-cases to populate the tool-scope picker.
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
            "Persist a project-specific fact, decision, or constraint as a memory entry. "
            "Use for information specific to this project or client — not for reusable patterns (use minder_skill_store for those)."
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
    ToolMeta(
        name="minder_memory_update",
        description=(
            "Update an existing memory entry's title, content, or tags. "
            "Call when a stored fact is known to be outdated or incorrect. Re-embeds automatically."
        ),
    ),
    ToolMeta(
        name="minder_memory_compact",
        description=(
            "Merge duplicate memory entries into a canonical entry. "
            "Only call when minder_memory_list shows more than 10 entries with visible overlap, "
            "or when the user explicitly asks to consolidate memories. Do not call proactively."
        ),
    ),
    # ── Skills ────────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_skill_store",
        description=(
            "Store a reusable workflow pattern, checklist, or code convention as a skill. "
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
        name="minder_skill_update",
        description=(
            "Update skill content, metadata, quality score, or deprecated status. "
            "Call after observing a skill's effectiveness: raise quality_score when it works well, "
            "set deprecated=True when it no longer applies."
        ),
    ),
    ToolMeta(
        name="minder_skill_delete",
        description="Delete a stored skill by its ID. Only call when explicitly asked to remove a skill.",
    ),
    ToolMeta(
        name="minder_skill_import_git",
        description=(
            "Admin: import skill documents from a remote Git repository and upsert them into the skill store. "
            "Operator/admin use only — do not call during normal agent workflows."
        ),
        scopeable=False,
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
        name="minder_workflow_get",
        description=(
            "Fetch the full workflow definition for a repository and sync repo-state files. "
            "Call once at session start to understand the complete workflow structure. "
            "For current step only, use minder_workflow_step (lighter)."
        ),
    ),
    ToolMeta(
        name="minder_workflow_step",
        description=(
            "Return the current workflow step and progress for a repository (lightweight). "
            "Call whenever you need to know where the workflow is right now. "
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
        name="minder_session_create",
        description=(
            "Create a named session for this project. Pass a stable slug (e.g. 'api-refactor-v2'). "
            "Call once at project start. On any later machine or after /compact, use minder_session_find instead."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_find",
        description=(
            "Find and load a session by name — the primary context-recovery tool. "
            "Call at the start of every session to recover prior state and resume work. "
            "Returns session_id, saved state, workflow position, and active skills."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_list",
        description=(
            "List all sessions owned by this principal (newest first). "
            "Use only when you do not know the session name. If you know the name, use minder_session_find."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_save",
        description=(
            "Checkpoint the current task state for an existing session. "
            "Call after each significant wave of work (decisions made, files changed, next steps planned). "
            "Do not wait until end of session — checkpoint frequently."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_restore",
        description=(
            "Reload saved state for a session by UUID. "
            "Use when you already have the session_id and need to reload state after a context loss. "
            "If you only have the project name, use minder_session_find instead."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_context",
        description=(
            "Update the active branch and open-file context for a session. "
            "Call when you switch branches or open new files to keep the session context accurate."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_summarize",
        description=(
            "Generate and persist a structured work summary for the session (task, steps completed, blockers, next actions). "
            "Call before /compact, before long gaps, or when the conversation grows long. "
            "This summary is recovered by minder_session_find on the next session."
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
        name="minder_auth_ping",
        description=(
            "Test MCP connectivity: returns 'auth pong'. "
            "Only call to verify authentication is working — not during normal workflows."
        ),
        scopeable=False,
        always_available=True,
    ),
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
            "Call once at session start to verify auth and understand available permissions."
        ),
        scopeable=False,
        always_available=True,
    ),
    ToolMeta(
        name="minder_auth_manage",
        description="Admin: list users and manage authentication records. Admin role required.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_create_client",
        description="Admin: create a new MCP client and issue its initial API key. Admin role required.",
        scopeable=False,
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
        description="Create or update (upsert) a SubAgent definition by name. Admin/operator use.",
        scopeable=True,
    ),
    ToolMeta(
        name="minder_agent_update",
        description="Partially update an existing SubAgent definition (title, description, system_prompt, tools, steps, tags).",
        scopeable=True,
    ),
    ToolMeta(
        name="minder_agent_delete",
        description="Delete a SubAgent definition by name. Admin use only.",
        scopeable=False,
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


TOOL_USAGE_PATTERNS: dict[str, str] = {
    # ── Session lifecycle ──────────────────────────────────────────────────────
    "minder_session_find": (
        "FIRST call at every session start — use project name to recover context. "
        "If found: cache the session_id and use it for all subsequent calls. "
        "If not found: call minder_session_create, then immediately save initial state."
    ),
    "minder_session_create": (
        "Call ONLY when minder_session_find returns no result. "
        "Pass a stable slug that won't change between machines (e.g. 'api-refactor-v2'). "
        "Do not create a new session if one already exists for the project."
    ),
    "minder_session_save": (
        "Call after EACH significant wave of work: after decisions, after changing files, after completing a step. "
        "Do not wait until end of session. Frequency: at minimum once per major action."
    ),
    "minder_session_summarize": (
        "Call proactively when the conversation exceeds ~20 exchanges, before any /compact, "
        "or before a long interruption. This summary is recovered on next session start."
    ),
    "minder_session_restore": (
        "Use only when you have the UUID from a previous response and need to reload state. "
        "If you only know the project name, use minder_session_find instead."
    ),
    "minder_session_context": (
        "Call whenever you switch git branches or open new files. "
        "Keeps the session context current so minder_session_summarize captures accurate state."
    ),
    "minder_session_cleanup": (
        "Only call when the user explicitly asks to purge old sessions. "
        "Never call proactively during normal work."
    ),
    # ── Workflow ───────────────────────────────────────────────────────────────
    "minder_workflow_guard": (
        "MANDATORY before starting or switching to ANY workflow step. "
        "If guard returns passed=false, do not proceed — surface the blocking reason to the user."
    ),
    "minder_workflow_step": (
        "Call when you need to know the current workflow position (lightweight). "
        "Prefer this over minder_workflow_get for simple 'what step am I on?' queries."
    ),
    "minder_workflow_get": (
        "Call once at session start to load the full workflow definition and sync repo-state files. "
        "Do not call repeatedly — the definition does not change during a session."
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
        "Do not use for reusable patterns or conventions — use minder_skill_store for those."
    ),
    "minder_memory_update": (
        "Call only when an existing memory is known to be wrong or outdated. "
        "Use minder_memory_list first to find the ID, then update."
    ),
    "minder_memory_compact": (
        "Only call when minder_memory_list returns more than 10 entries with visible overlap, "
        "or when the user explicitly asks to consolidate memories. Never call proactively."
    ),
    # ── Skills ────────────────────────────────────────────────────────────────
    "minder_skill_recall": (
        "Call at the START of each workflow step to load applicable patterns, checklists, and conventions. "
        "Always pass current_step so step-compatible skills rank first. "
        "Do not use for project-specific facts — use minder_memory_recall for those."
    ),
    "minder_skill_store": (
        "Call when a reusable workflow pattern, checklist, code template, or convention is identified. "
        "Must be applicable across projects — project-specific knowledge belongs in memory."
    ),
    "minder_skill_update": (
        "Call after observing a skill's effectiveness: "
        "raise quality_score (0.0–1.0) when it produces good outcomes, lower it when it misleads. "
        "Set deprecated=True when a skill is no longer applicable."
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
        "Session startup sequence: minder_session_find → (if not found) minder_session_create → minder_workflow_step → minder_skill_recall → minder_memory_recall.",
        "Repo-scoped tools (search_code, search_graph, find_impact, workflow_*) require repo_path or repo_id.",
        "Read minder://instructions for the complete sequencing guide before calling any tools.",
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
            "User account records are read-only. Minder may inspect identity information through read-only auth tools such as whoami or list_users, but it must not claim it can create, edit, rotate, deactivate, or delete users.",
            "Repository-aware search, graph traversal, and query actions require repository context before they can inspect code or graph state.",
            "If a request asks what Minder can do, answer from the tool capability manifest instead of saying no tools are available.",
        ]
    )
