from __future__ import annotations

from typing import Any

from minder.runtime import load_attr, module_available


def graph_runtime_name(preferred: str = "langgraph") -> str:
    if preferred == "langgraph" and module_available("langgraph"):
        return "langgraph"
    return "internal"


def load_langgraph_state_graph() -> Any | None:
    return load_attr("langgraph.graph", "StateGraph")
