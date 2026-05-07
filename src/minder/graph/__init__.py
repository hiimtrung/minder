from .state import GraphState, GraphStateSchema

__all__ = ["GraphState", "GraphStateSchema", "MinderGraph"]


def __getattr__(name: str):
    if name == "MinderGraph":
        from .graph import MinderGraph

        return MinderGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
