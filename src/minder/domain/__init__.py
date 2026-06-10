"""
Domain Layer — Clean Architecture innermost layer.

This package contains:
- entities/     Pure domain models (no ORM, no framework dependencies)
- interfaces/   Protocol classes defining contracts for infrastructure
- exceptions.py Domain-specific exceptions
- value_objects.py  Enums, constants, and value types
"""

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
    "SCOPEABLE_TOOLS",
    "ALWAYS_AVAILABLE_FOR_CLIENTS",
    "DEFAULT_AGENT_TOOL_SCOPES",
    "TOOL_DESCRIPTIONS",
    "TOOL_USAGE_PATTERNS",
    "tool_capability_manifest",
    "tool_data_access_policy",
]

