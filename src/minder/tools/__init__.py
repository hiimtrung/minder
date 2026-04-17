from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .auth import AuthTools
    from .ingest import IngestTools
    from .memory import MemoryTools
    from .query import QueryTools
    from .repo_scanner import RepoScanner
    from .search import SearchTools
    from .session import SessionTools
    from .workflow import WorkflowTools

__all__ = [
    "AuthTools",
    "IngestTools",
    "MemoryTools",
    "QueryTools",
    "RepoScanner",
    "SearchTools",
    "SessionTools",
    "WorkflowTools",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AuthTools": (".auth", "AuthTools"),
    "IngestTools": (".ingest", "IngestTools"),
    "MemoryTools": (".memory", "MemoryTools"),
    "QueryTools": (".query", "QueryTools"),
    "RepoScanner": (".repo_scanner", "RepoScanner"),
    "SearchTools": (".search", "SearchTools"),
    "SessionTools": (".session", "SessionTools"),
    "WorkflowTools": (".workflow", "WorkflowTools"),
}


def __getattr__(name: str) -> Any:
    module_spec = _LAZY_EXPORTS.get(name)
    if module_spec is None:
        raise AttributeError(name)
    module_name, symbol_name = module_spec
    module = import_module(module_name, __name__)
    value = getattr(module, symbol_name)
    globals()[name] = value
    return value
