"""
RepoScanner — walk a repository and write module-dependency nodes/edges
into a KnowledgeGraphStore.

Supported source languages:
- Python: imports parsed via the standard-library ``ast`` module.

Service boundary detection:
- A directory containing ``pyproject.toml`` or ``package.json`` is
  treated as a service root.  A ``service`` node is created and each
  file inside inherits a ``belongs_to`` edge pointing to that service.

All writes are idempotent (upsert).  Re-scanning the same repo updates
existing nodes/edges without creating duplicates.

Node types produced
-------------------
``file``    — every ingested source file (name = relative path).
``module``  — every Python module referenced in an import statement
              (name = dotted module path, e.g. ``minder.store.graph``).
``service`` — every directory that contains ``pyproject.toml`` /
              ``package.json``.

Edge relations produced
-----------------------
``imports``     — file → module  (file imports that module).
``contains``    — service → file (file lives inside the service).
``depends_on``  — service → service (cross-service import detected).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from minder.store.graph import KnowledgeGraphStore

# File extensions considered Python source.
_PYTHON_SUFFIXES = {".py"}

# Filenames that mark a service-boundary directory.
_SERVICE_MARKERS = {"pyproject.toml", "package.json"}


class RepoScanner:
    """Scan a local repository and populate a :class:`KnowledgeGraphStore`.

    Args:
        graph_store: An initialised (``init_db`` already called) graph store.
        repo_root:   Absolute path to the repository root.
        project:     Optional project label embedded in node metadata.
    """

    def __init__(
        self,
        graph_store: KnowledgeGraphStore,
        repo_root: str,
        *,
        project: str | None = None,
    ) -> None:
        self._store = graph_store
        self._root = Path(repo_root).resolve()
        self._project = project or self._root.name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(self) -> dict[str, Any]:
        """Walk the repo, build the graph, return a summary.

        Returns:
            A dict with keys ``project``, ``files_scanned``,
            ``nodes_upserted``, ``edges_upserted``.
        """
        service_dirs = self._discover_service_boundaries()
        python_files = self._discover_python_files()

        nodes_upserted = 0
        edges_upserted = 0

        # Upsert service nodes first (so file→service edges can reference them).
        service_node_ids: dict[Path, Any] = {}
        for svc_dir in service_dirs:
            rel = str(svc_dir.relative_to(self._root))
            svc_node = await self._store.upsert_node(
                node_type="service",
                name=rel,
                metadata={"project": self._project, "path": str(svc_dir)},
            )
            service_node_ids[svc_dir] = svc_node.id
            nodes_upserted += 1

        # Process each Python file.
        for file_path in python_files:
            rel_path = str(file_path.relative_to(self._root))

            # Upsert file node.
            file_node = await self._store.upsert_node(
                node_type="file",
                name=rel_path,
                metadata={"project": self._project, "language": "python"},
            )
            nodes_upserted += 1

            # Link file to its enclosing service (innermost match).
            owning_svc = self._find_owning_service(file_path, service_dirs)
            if owning_svc is not None:
                svc_node_id = service_node_ids[owning_svc]
                await self._store.upsert_edge(
                    source_id=svc_node_id,
                    target_id=file_node.id,
                    relation="contains",
                )
                edges_upserted += 1

            # Parse imports and create module nodes + edges.
            imports = self._extract_imports(file_path)
            for module_name in imports:
                mod_node = await self._store.upsert_node(
                    node_type="module",
                    name=module_name,
                    metadata={"project": self._project},
                )
                nodes_upserted += 1

                await self._store.upsert_edge(
                    source_id=file_node.id,
                    target_id=mod_node.id,
                    relation="imports",
                )
                edges_upserted += 1

                # Cross-service dependency detection:
                # If the imported module's top-level package matches another
                # service's directory name, add a depends_on edge.
                if owning_svc is not None:
                    top_pkg = module_name.split(".")[0]
                    for svc_dir, svc_node_id in service_node_ids.items():
                        if svc_dir != owning_svc and svc_dir.name == top_pkg:
                            await self._store.upsert_edge(
                                source_id=service_node_ids[owning_svc],
                                target_id=svc_node_id,
                                relation="depends_on",
                            )
                            edges_upserted += 1

        return {
            "project": self._project,
            "files_scanned": len(python_files),
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
        }

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    def _discover_service_boundaries(self) -> list[Path]:
        """Return directories that contain a service-marker file, sorted
        so innermost directories come first (longest path first)."""
        service_dirs: list[Path] = []
        for marker in _SERVICE_MARKERS:
            for marker_path in self._root.rglob(marker):
                # Skip hidden directories.
                if any(part.startswith(".") for part in marker_path.parts):
                    continue
                svc_dir = marker_path.parent
                if svc_dir not in service_dirs:
                    service_dirs.append(svc_dir)
        # Sort by depth (deepest first) so _find_owning_service returns innermost.
        return sorted(service_dirs, key=lambda p: len(p.parts), reverse=True)

    def _discover_python_files(self) -> list[Path]:
        """Return all Python source files under the repo root, skipping
        hidden directories and ``__pycache__``."""
        files: list[Path] = []
        for path in self._root.rglob("*.py"):
            if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
                continue
            files.append(path)
        return sorted(files)

    @staticmethod
    def _find_owning_service(
        file_path: Path, service_dirs: list[Path]
    ) -> Path | None:
        """Return the innermost service directory that is an ancestor of
        *file_path*, or ``None`` if none match."""
        for svc_dir in service_dirs:  # already sorted deepest-first
            try:
                file_path.relative_to(svc_dir)
                return svc_dir
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # AST import extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_imports(file_path: Path) -> list[str]:
        """Parse *file_path* with ``ast`` and return a deduplicated list of
        imported module names.

        - ``import os`` → ``["os"]``
        - ``from pathlib import Path`` → ``["pathlib"]``
        - ``from minder.store import graph`` → ``["minder.store"]``

        Returns an empty list if the file cannot be parsed (syntax error,
        encoding error, etc.).
        """
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, ValueError):
            return []

        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module)
        return sorted(modules)
