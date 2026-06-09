"""
Tool Registry — single source of truth for tool names, descriptions, and scope metadata.

Import TOOL_DESCRIPTIONS in bootstrap/transport.py to register tools.
Import SCOPEABLE_TOOLS in admin use-cases to populate the tool-scope picker.
"""

from __future__ import annotations

from minder.domain.value_objects import (
    ALL_TOOLS,
    ALWAYS_AVAILABLE_FOR_CLIENTS,
    DEFAULT_AGENT_TOOL_SCOPES,
    SCOPEABLE_TOOLS,
    TOOL_DESCRIPTIONS,
    TOOL_USAGE_PATTERNS,
    ToolMeta,
    tool_capability_manifest,
    tool_data_access_policy,
)

__all__ = [
    "ToolMeta",
    "ALL_TOOLS",
    "ALWAYS_AVAILABLE_FOR_CLIENTS",
    "DEFAULT_AGENT_TOOL_SCOPES",
    "SCOPEABLE_TOOLS",
    "TOOL_DESCRIPTIONS",
    "TOOL_USAGE_PATTERNS",
    "tool_capability_manifest",
    "tool_data_access_policy",
]
