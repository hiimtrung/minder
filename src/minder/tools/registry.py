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
        description="Store a memory entry with title, content, tags, and language metadata.",
    ),
    ToolMeta(
        name="minder_memory_recall",
        description="Search stored memory entries by semantic similarity.",
    ),
    ToolMeta(
        name="minder_memory_list",
        description="List the currently stored memory entries.",
    ),
    ToolMeta(
        name="minder_memory_delete",
        description="Delete a stored memory entry by its ID.",
    ),
    ToolMeta(
        name="minder_memory_compact",
        description="Review and compact duplicate memory entries by merging selected memories into a canonical entry.",
    ),
    ToolMeta(
        name="minder_skill_store",
        description="Store a reusable workflow-aware skill with step, artifact, provenance, and quality metadata.",
    ),
    ToolMeta(
        name="minder_skill_recall",
        description="Retrieve reusable skills ranked by workflow-step compatibility, semantic similarity, and quality score.",
    ),
    ToolMeta(
        name="minder_skill_list",
        description="List stored skills with optional workflow-step, tag, and quality filters.",
    ),
    ToolMeta(
        name="minder_skill_update",
        description="Update skill content, metadata, and quality signals for an existing stored skill.",
    ),
    ToolMeta(
        name="minder_skill_delete",
        description="Delete a stored skill by its ID.",
    ),
    ToolMeta(
        name="minder_skill_import_git",
        description="Import supported skill documents from a Git repository path and upsert them with source metadata.",
    ),
    # ── Search & Query ────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_search",
        description="Search Minder knowledge and stored project context.",
    ),
    ToolMeta(
        name="minder_search_code",
        description="Search indexed repository code for relevant files and snippets.",
    ),
    ToolMeta(
        name="minder_search_errors",
        description="Search indexed errors and troubleshooting history for relevant matches.",
    ),
    ToolMeta(
        name="minder_query",
        description="Run a full Minder repository query with retrieval, reasoning, and verification.",
    ),
    ToolMeta(
        name="minder_find_impact",
        description="Traverse the repository graph to show upstream and downstream impact for a file, symbol, route, or dependency.",
    ),
    ToolMeta(
        name="minder_search_graph",
        description="Search the repository graph for matching files, symbols, routes, todos, or dependencies within a repo scope.",
    ),
    # ── Workflow ──────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_workflow_get",
        description="Fetch the workflow assigned to a repository and sync repo-state files.",
    ),
    ToolMeta(
        name="minder_workflow_step",
        description="Return the current workflow step for a repository and sync repo-state files.",
    ),
    ToolMeta(
        name="minder_workflow_update",
        description="Mark a workflow step complete and optionally persist an artifact for the repository.",
    ),
    ToolMeta(
        name="minder_workflow_guard",
        description="Check whether a requested workflow step is currently allowed for the repository.",
    ),
    # ── Session ───────────────────────────────────────────────────────────────
    ToolMeta(
        name="minder_session_create",
        description=(
            "Create a named, persisted Minder session for the calling principal. "
            "Pass a stable project slug as 'name' (e.g. 'omi-channel-phase5') so the "
            "session can be recovered from any machine using the same client API key."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_find",
        description=(
            "Find a session by name for the calling principal — the primary cross-environment "
            "recovery tool. Returns full state and context so the LLM can resume after a "
            "/compact or machine switch without needing to remember the session UUID."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_list",
        description=(
            "List all sessions owned by the calling principal, newest-first. "
            "Use minder_session_find when you know the session name."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_save",
        description=(
            "Persist task state and active skill context for an existing session. "
            "Call after each significant wave of work so context survives /compact."
        ),
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_restore",
        description="Load saved state and context for an existing session by UUID.",
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_context",
        description="Update branch and open-file context for an existing Minder session.",
        always_available=True,
    ),
    ToolMeta(
        name="minder_session_cleanup",
        description="Delete expired sessions owned by the calling principal and remove their persisted history records.",
        always_available=True,
    ),
    # ── Auth (internal — not grantable to client principals) ─────────────────
    ToolMeta(
        name="minder_auth_ping",
        description="Verify that MCP authentication is working and the current principal can reach protected tools.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_login",
        description="Exchange a human admin API key for a JWT bearer token.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_exchange_client_key",
        description="Exchange a client API key for a scoped client access token.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_whoami",
        description="Return the authenticated principal identity, role, and any active scopes.",
        scopeable=False,
        always_available=True,
    ),
    ToolMeta(
        name="minder_auth_manage",
        description="Run admin-only authentication management actions such as listing registered users.",
        scopeable=False,
    ),
    ToolMeta(
        name="minder_auth_create_client",
        description="Create a new MCP client and issue its initial client API key.",
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


def _tool_category(tool_name: str) -> str:
    if tool_name.startswith("minder_memory_"):
        return "Memory"
    if tool_name.startswith("minder_skill_"):
        return "Skills"
    if tool_name.startswith("minder_search_") or tool_name in {
        "minder_search",
        "minder_query",
        "minder_find_impact",
    }:
        return "Search and query"
    if tool_name.startswith("minder_workflow_"):
        return "Workflow"
    if tool_name.startswith("minder_session_"):
        return "Sessions"
    if tool_name.startswith("minder_auth_"):
        return "Auth and identity"
    return "Other"


def tool_capability_manifest() -> str:
    grouped: dict[str, list[ToolMeta]] = {}
    for tool in ALL_TOOLS:
        grouped.setdefault(_tool_category(tool.name), []).append(tool)

    ordered_categories = [
        "Memory",
        "Skills",
        "Search and query",
        "Workflow",
        "Sessions",
        "Auth and identity",
        "Other",
    ]
    lines = [
        "Minder has built-in tools and internal data capabilities even when no repository is selected.",
        "Repo-scoped query, graph, and impact tools need a repository path or repository selection before they can inspect code context.",
    ]
    for category in ordered_categories:
        tools = grouped.get(category, [])
        if not tools:
            continue
        lines.append(f"{category}:")
        for tool in tools:
            availability = (
                "always available to authenticated clients"
                if tool.always_available
                else "scoped" if tool.scopeable else "admin/internal"
            )
            lines.append(f"- {tool.name}: {tool.description} [{availability}]")
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
