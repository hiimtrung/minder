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
