from .state import GraphState

__all__ = ["GraphState", "MinderGraph"]


def __getattr__(name: str):
    if name == "MinderGraph":
        from .graph import MinderGraph

        return MinderGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
