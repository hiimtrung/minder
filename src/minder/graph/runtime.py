from __future__ import annotations

from minder.runtime import module_available


def graph_runtime_name(preferred: str = "langgraph") -> str:
    if preferred == "langgraph" and module_available("langgraph"):
        return "langgraph"
    return "internal"
