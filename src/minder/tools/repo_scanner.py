"""Repository graph extraction and sync-payload building."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import concurrent.futures
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from minder.store.graph import KnowledgeGraphStore

_SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".md",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}
_PYTHON_SUFFIXES = {".py"}
_SCRIPT_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs"}
_MARKDOWN_SUFFIXES = {".md"}
_STRUCTURED_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
_SERVICE_MARKERS = {"pyproject.toml", "package.json", "go.mod", "Cargo.toml"}
_HTTP_ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "route"}
_MQ_PUBLISH_CALLS = {"publish", "send", "produce", "emit"}
_MQ_CONSUME_CALLS = {"consume", "subscribe", "listen"}
_DEFAULT_IGNORE_DIRS = {
    "node_modules", "dist", "build", "target", "vendor", "venv", ".venv",
    ".git", ".idea", ".vscode", "__pycache__", ".next", ".cache", "out"
}

# Spring Boot route annotation detection (Java)
_SPRING_ROUTE_PATTERN = re.compile(
    r'@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)'
    r'\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']',
    re.MULTILINE,
)
# NestJS decorator detection (TypeScript) — @Get/@Post etc. at class level prefix
_NESTJS_CONTROLLER_PATTERN = re.compile(
    r'@Controller\s*\(\s*["\']([^"\']*)["\']',
    re.MULTILINE,
)
_NESTJS_ROUTE_PATTERN = re.compile(
    r'@(Get|Post|Put|Patch|Delete|All)\s*\(\s*(?:["\']([^"\']*)["\'])?\s*\)',
    re.MULTILINE,
)
# WebSocket endpoint detection
_WS_GATEWAY_PATTERN = re.compile(
    r'@WebSocketGateway\s*\(\s*(?:(?:path\s*=\s*)?["\']([^"\']*)["\'])?\s*\)',
    re.MULTILINE,
)
_WS_SUBSCRIBE_PATTERN = re.compile(
    r'@SubscribeMessage\s*\(\s*["\']([^"\']+)["\']',
    re.MULTILINE,
)
_SPRING_WS_MAPPING_PATTERN = re.compile(
    r'@MessageMapping\s*\(\s*["\']([^"\']+)["\']',
    re.MULTILINE,
)
# Go/Gin/Fiber route patterns
_GO_ROUTE_PATTERN = re.compile(
    r'(?:r|router|app|engine)\.(GET|POST|PUT|PATCH|DELETE)\s*\(\s*"([^"]+)"',
    re.MULTILINE,
)
# Rust/axum/actix-web route patterns
_RUST_ROUTE_ATTR_PATTERN = re.compile(
    r'#\[(?:get|post|put|patch|delete)\s*\(\s*"([^"]+)"\s*\)\]',
    re.MULTILINE,
)
_TODO_PATTERN = re.compile(r"(?:#|//|/\*+|\*+)\s*TODO\s*:?\s*(.+)?", re.IGNORECASE)
_MARKDOWN_TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[\s\]\s+(.+)$")
_URL_PATTERN = re.compile(r"https?://[^\s\"')]+")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_YAML_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)\s*:", re.MULTILINE)
_INI_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)\s*=", re.MULTILINE)
_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".md": "markdown",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "text",
}


@dataclass(slots=True)
class _NodeSpec:
    node_type: str
    name: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class _EdgeSpec:
    source_type: str
    source_name: str
    target_type: str
    target_name: str
    relation: str
    weight: float = 1.0


class RepoScanner:
    def __init__(
        self,
        graph_store: "KnowledgeGraphStore",
        repo_root: str,
        *,
        project: str | None = None,
    ) -> None:
        self._store = graph_store
        self._root = Path(repo_root).resolve()
        self._project = project or self._root.name
        self._git_metadata_cache: dict[str, dict[str, Any]] = {}
        self._git_line_commit_cache: dict[tuple[str, int], dict[str, str] | None] = {}
        self._git_commit_detail_cache: dict[str, dict[str, str]] = {}
        self._git_file_blame_cache: dict[str, dict[int, str]] = {}
        self._git_enabled = True

    def _run_git(
        self,
        args: list[str],
        *,
        capture_output: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if not self._git_enabled:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._root,
                capture_output=capture_output,
                text=True,
                check=check,
            )
        except FileNotFoundError:
            self._git_enabled = False
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    async def scan(self) -> dict[str, Any]:
        service_dirs = self._discover_service_boundaries()
        source_files = self._discover_source_files()

        nodes_upserted = 0
        edges_upserted = 0
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

        for file_path in source_files:
            rel_path = str(file_path.relative_to(self._root))
            file_metadata, extracted_nodes, extracted_edges = self._extract_file_metadata(file_path, rel_path)
            change_metadata = self._git_file_change_metadata(rel_path)
            common_metadata = self._build_file_scoped_metadata(
                rel_path=rel_path,
                language=str(file_metadata.get("language", "text") or "text"),
                change_metadata=change_metadata,
            )

            file_node = await self._store.upsert_node(
                node_type="file",
                name=rel_path,
                metadata={"project": self._project, **common_metadata, **file_metadata},
            )
            nodes_upserted += 1
            known_node_ids: dict[tuple[str, str], Any] = {("file", rel_path): file_node.id}

            owning_svc = self._find_owning_service(file_path, service_dirs)
            if owning_svc is not None:
                await self._store.upsert_edge(
                    source_id=service_node_ids[owning_svc],
                    target_id=file_node.id,
                    relation="contains",
                )
                edges_upserted += 1

            for module_name in self._extract_imports(file_path):
                mod_node = await self._store.upsert_node(
                    node_type="module",
                    name=module_name,
                    metadata={"project": self._project},
                )
                nodes_upserted += 1
                known_node_ids[("module", module_name)] = mod_node.id

                await self._store.upsert_edge(
                    source_id=file_node.id,
                    target_id=mod_node.id,
                    relation="imports",
                )
                edges_upserted += 1

                if owning_svc is not None:
                    top_pkg = module_name.split(".")[0].split("/")[0].split(":")[0]
                    for svc_dir, svc_node_id in service_node_ids.items():
                        if svc_dir != owning_svc and svc_dir.name == top_pkg:
                            await self._store.upsert_edge(
                                source_id=service_node_ids[owning_svc],
                                target_id=svc_node_id,
                                relation="depends_on",
                            )
                            edges_upserted += 1

            for node_spec in extracted_nodes:
                node_common_metadata = self._build_node_scoped_metadata(
                    rel_path=rel_path,
                    base_metadata=common_metadata,
                    node_metadata=node_spec.metadata,
                )
                persisted = await self._store.upsert_node(
                    node_type=node_spec.node_type,
                    name=node_spec.name,
                    metadata={"project": self._project, **node_common_metadata, **node_spec.metadata},
                )
                known_node_ids[(node_spec.node_type, node_spec.name)] = persisted.id
                nodes_upserted += 1

            for edge_spec in extracted_edges:
                source_id = known_node_ids.get((edge_spec.source_type, edge_spec.source_name))
                target_id = known_node_ids.get((edge_spec.target_type, edge_spec.target_name))
                if source_id is None or target_id is None:
                    continue
                await self._store.upsert_edge(
                    source_id=source_id,
                    target_id=target_id,
                    relation=edge_spec.relation,
                    weight=edge_spec.weight,
                )
                edges_upserted += 1

        return {
            "project": self._project,
            "files_scanned": len(source_files),
            "nodes_upserted": nodes_upserted,
            "edges_upserted": edges_upserted,
        }

    @classmethod
    def build_sync_payload(
        cls,
        repo_root: str,
        *,
        project: str | None = None,
        branch: str | None = None,
        diff_base: str | None = None,
        changed_files: list[str] | None = None,
        deleted_files: list[str] | None = None,
        branch_relationships: list[dict[str, Any]] | None = None,
        payload_version: str = "2026-04-15",
        source: str = "minder-cli",
        commit_hash: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        builder = cls.__new__(cls)
        builder._root = Path(repo_root).resolve()
        builder._project = project or builder._root.name
        builder._git_metadata_cache = {}
        builder._git_line_commit_cache = {}
        builder._git_commit_detail_cache = {}
        builder._git_file_blame_cache = {}
        builder._git_enabled = True

        if progress_callback:
            progress_callback("Discovering service boundaries...")
        service_dirs = builder._discover_service_boundaries()
        if progress_callback:
            progress_callback(f"Resolving source files (diff_base={diff_base})...")
        source_files = builder._resolve_source_files(changed_files)
        if progress_callback:
            progress_callback(f"Found {len(source_files)} files to scan.")
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[tuple[str, str]] = set()
        seen_edges: set[tuple[str, str, str, str, str]] = set()

        def add_node(node_type: str, name: str, metadata: dict[str, Any]) -> None:
            key = (node_type, name)
            if key in seen_nodes:
                for existing in nodes:
                    if existing["node_type"] == node_type and existing["name"] == name:
                        existing["metadata"] = {**existing["metadata"], **metadata}
                        return
            seen_nodes.add(key)
            nodes.append({"node_type": node_type, "name": name, "metadata": metadata})

        def add_edge(edge_spec: _EdgeSpec) -> None:
            key = (
                edge_spec.source_type,
                edge_spec.source_name,
                edge_spec.target_type,
                edge_spec.target_name,
                edge_spec.relation,
            )
            if key in seen_edges:
                return
            seen_edges.add(key)
            edges.append(
                {
                    "source": {"node_type": edge_spec.source_type, "name": edge_spec.source_name},
                    "target": {"node_type": edge_spec.target_type, "name": edge_spec.target_name},
                    "relation": edge_spec.relation,
                    "weight": edge_spec.weight,
                }
            )

        def process_file(i: int, file_path: Path) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
            rel_path = str(file_path.relative_to(builder._root))
            file_nodes: list[dict[str, Any]] = []
            file_edges: list[dict[str, Any]] = []

            def local_add_node(node_type: str, name: str, metadata: dict[str, Any]) -> None:
                file_nodes.append({"node_type": node_type, "name": name, "metadata": metadata})

            def local_add_edge(edge_spec: _EdgeSpec) -> None:
                file_edges.append(
                    {
                        "source": {"node_type": edge_spec.source_type, "name": edge_spec.source_name},
                        "target": {"node_type": edge_spec.target_type, "name": edge_spec.target_name},
                        "relation": edge_spec.relation,
                        "weight": edge_spec.weight,
                    }
                )

            file_metadata, extracted_nodes, extracted_edges = builder._extract_file_metadata(file_path, rel_path)
            change_metadata = builder._git_file_change_metadata(rel_path)
            common_metadata = builder._build_file_scoped_metadata(
                rel_path=rel_path,
                language=str(file_metadata.get("language", "text") or "text"),
                change_metadata=change_metadata,
            )
            local_add_node("file", rel_path, {"project": builder._project, **common_metadata, **file_metadata})

            owning_svc = builder._find_owning_service(file_path, service_dirs)
            if owning_svc is not None:
                service_rel_path = str(owning_svc.relative_to(builder._root))
                local_add_node("service", service_rel_path, {"project": builder._project, "path": service_rel_path})
                local_add_edge(_EdgeSpec("service", service_rel_path, "file", rel_path, "contains"))

            for module_name in builder._extract_imports(file_path):
                local_add_node("module", module_name, {"project": builder._project})
                local_add_edge(_EdgeSpec("file", rel_path, "module", module_name, "imports"))

            for node_spec in extracted_nodes:
                node_common_metadata = builder._build_node_scoped_metadata(
                    rel_path=rel_path,
                    base_metadata=common_metadata,
                    node_metadata=node_spec.metadata,
                )
                local_add_node(
                    node_spec.node_type,
                    node_spec.name,
                    {"project": builder._project, **node_common_metadata, **node_spec.metadata}
                )

            for edge_spec in extracted_edges:
                local_add_edge(edge_spec)
            
            return i, file_nodes, file_edges

        # Use ThreadPoolExecutor for parallel scanning
        import os
        max_workers = min(32, (os.cpu_count() or 4) * 4)
        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_file, i, file_path) for i, file_path in enumerate(source_files)]
            for future in concurrent.futures.as_completed(futures):
                i, file_nodes, file_edges = future.result()
                completed_count += 1
                if progress_callback and completed_count % 10 == 0:
                    progress_callback(f"[{completed_count}/{len(source_files)}] Scanned {str(source_files[i].relative_to(builder._root))}")
                
                for node in file_nodes:
                    add_node(node["node_type"], node["name"], node["metadata"])
                for edge in file_edges:
                    # Construct _EdgeSpec from dict for add_edge
                    spec = _EdgeSpec(
                        source_type=edge["source"]["node_type"],
                        source_name=edge["source"]["name"],
                        target_type=edge["target"]["node_type"],
                        target_name=edge["target"]["name"],
                        relation=edge["relation"],
                        weight=edge["weight"]
                    )
                    add_edge(spec)

        if progress_callback:
            progress_callback(
                f"Scan complete. Found {len(nodes)} nodes and {len(edges)} edges."
            )

        return {
            "payload_version": payload_version,
            "source": source,
            "repo_path": str(builder._root),
            "branch": branch,
            "diff_base": diff_base,
            "changed_files": [str(file_path.relative_to(builder._root)) for file_path in source_files],
            "deleted_files": sorted(deleted_files or []),
            "commit_hash": commit_hash,
            "sync_metadata": {
                "project": builder._project,
                "changed_file_count": len(source_files),
                "deleted_file_count": len(deleted_files or []),
                "branch_relationship_count": len(branch_relationships or []),
            },
            "nodes": nodes,
            "edges": edges,
            "branch_relationships": list(branch_relationships or []),
        }

    def _discover_service_boundaries(self) -> list[Path]:
        service_dirs: set[Path] = set()
        
        if self._git_enabled:
            # Use git ls-files for much better performance on large repos
            patterns = [f"**/{m}" for m in _SERVICE_MARKERS]
            result = self._run_git(["ls-files", "--", *patterns], check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line:
                        service_dirs.add((self._root / line).parent)
                if service_dirs:
                    return sorted(list(service_dirs), key=lambda path: len(path.parts), reverse=True)

        # Fallback with manual walk to prune ignored directories efficiently
        import os
        for root, dirs, files in os.walk(self._root):
            # Prune ignored directories in-place to avoid descending into them
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _DEFAULT_IGNORE_DIRS]
            for file in files:
                if file in _SERVICE_MARKERS:
                    service_dirs.add(Path(root))
                    
        return sorted(list(service_dirs), key=lambda path: len(path.parts), reverse=True)

    def _discover_source_files(self) -> list[Path]:
        files: list[Path] = []
        
        if self._git_enabled:
            # Combined tracked and untracked files with matching suffixes
            patterns = [f"**/*{s}" for s in _SOURCE_SUFFIXES]
            result = self._run_git(["ls-files", "--cached", "--others", "--exclude-standard", "--", *patterns], check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line:
                        files.append(self._root / line)
                if files:
                    return sorted(set(files))

        # Fallback with pruned walk
        import os
        for root, dirs, filenames in os.walk(self._root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _DEFAULT_IGNORE_DIRS]
            for filename in filenames:
                path = Path(root) / filename
                if path.suffix.lower() in _SOURCE_SUFFIXES:
                    files.append(path)
        return sorted(set(files))

    def _resolve_source_files(self, changed_files: list[str] | None) -> list[Path]:
        if changed_files is None:
            return self._discover_source_files()
        files: list[Path] = []
        for changed_file in changed_files:
            candidate = (self._root / changed_file).resolve()
            if candidate.is_file() and candidate.suffix.lower() in _SOURCE_SUFFIXES:
                files.append(candidate)
        return sorted(set(files))

    @staticmethod
    def _find_owning_service(file_path: Path, service_dirs: list[Path]) -> Path | None:
        for svc_dir in service_dirs:
            try:
                file_path.relative_to(svc_dir)
                return svc_dir
            except ValueError:
                continue
        return None

    def _extract_file_metadata(
        self,
        file_path: Path,
        rel_path: str,
    ) -> tuple[dict[str, Any], list[_NodeSpec], list[_EdgeSpec]]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        suffix = file_path.suffix.lower()
        language = _LANGUAGE_BY_SUFFIX.get(suffix, suffix.lstrip("."))
        file_metadata: dict[str, Any] = {
            "path": rel_path,
            "language": language,
            "line_count": source.count("\n") + (1 if source else 0),
            "size_bytes": file_path.stat().st_size,
        }
        nodes: list[_NodeSpec] = []
        edges: list[_EdgeSpec] = []

        if suffix in _PYTHON_SUFFIXES:
            python_nodes, python_edges = self._extract_python_metadata(file_path, rel_path)
            nodes.extend(python_nodes)
            edges.extend(python_edges)
        elif suffix in _SCRIPT_SUFFIXES:
            script_metadata, script_nodes, script_edges = self._extract_script_metadata(source, rel_path)
            file_metadata.update(script_metadata)
            nodes.extend(script_nodes)
            edges.extend(script_edges)
        elif suffix in _MARKDOWN_SUFFIXES:
            file_metadata.update(self._extract_markdown_metadata(source))
            nodes.extend(self._extract_markdown_task_nodes(source, rel_path))
        elif suffix in _STRUCTURED_SUFFIXES:
            file_metadata.update(self._extract_structured_metadata(source, suffix))
        else:
            file_metadata["non_empty_line_count"] = len([line for line in source.splitlines() if line.strip()])

        nodes.extend(self._extract_todo_nodes(source, rel_path))
        return file_metadata, self._dedupe_node_specs(nodes), self._dedupe_edge_specs(edges)

    def _build_file_scoped_metadata(
        self,
        *,
        rel_path: str,
        language: str,
        change_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "path": rel_path,
            "language": language,
            "history_scope": "file",
            **change_metadata,
        }

    def _build_node_scoped_metadata(
        self,
        *,
        rel_path: str,
        base_metadata: dict[str, Any],
        node_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        scoped_metadata = dict(base_metadata)
        scoped_metadata.update(
            self._git_node_change_metadata(
                rel_path=rel_path,
                node_metadata=node_metadata,
                file_change_metadata=base_metadata,
            )
        )
        return scoped_metadata

    def _git_file_change_metadata(self, rel_path: str) -> dict[str, Any]:
        cached = self._git_metadata_cache.get(rel_path)
        if cached is not None:
            return cached

        recent_commits = self._git_recent_commits(rel_path)
        status = self._git_status(rel_path, tracked=bool(recent_commits))
        latest_commit = recent_commits[0] if recent_commits else {}
        metadata = {
            "last_state": status,
            "last_commit_sha": latest_commit.get("sha"),
            "last_commit_at": latest_commit.get("committed_at"),
            "last_commit_summary": latest_commit.get("summary"),
            "history_summary": self._build_history_summary(recent_commits, status),
            "recent_commits": recent_commits,
        }
        self._git_metadata_cache[rel_path] = metadata
        return metadata

    def _git_node_change_metadata(
        self,
        *,
        rel_path: str,
        node_metadata: dict[str, Any],
        file_change_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        line_number = self._node_line_number(node_metadata)
        if line_number is None:
            return {}

        line_commit = self._git_line_commit(rel_path, line_number)
        if line_commit is None:
            return {
                "history_scope": "line",
                "last_touch_line": line_number,
                "file_last_commit_sha": file_change_metadata.get("last_commit_sha"),
                "file_last_commit_at": file_change_metadata.get("last_commit_at"),
                "file_last_commit_summary": file_change_metadata.get("last_commit_summary"),
                "file_history_summary": file_change_metadata.get("history_summary"),
            }

        subject = self._history_subject(node_metadata)
        recent_commits = self._build_symbol_recent_commits(
            subject=subject,
            line_commit=line_commit,
            file_recent_commits=file_change_metadata.get("recent_commits"),
        )
        return {
            "history_scope": "symbol" if subject else "line",
            "last_touch_line": line_number,
            "last_commit_sha": line_commit.get("sha"),
            "last_commit_at": line_commit.get("committed_at"),
            "last_commit_summary": line_commit.get("summary"),
            "history_summary": self._build_symbol_history_summary(
                subject=subject,
                status=str(file_change_metadata.get("last_state", "") or ""),
                line_commit=line_commit,
                recent_commits=recent_commits,
            ),
            "recent_commits": recent_commits,
            "file_last_commit_sha": file_change_metadata.get("last_commit_sha"),
            "file_last_commit_at": file_change_metadata.get("last_commit_at"),
            "file_last_commit_summary": file_change_metadata.get("last_commit_summary"),
            "file_history_summary": file_change_metadata.get("history_summary"),
        }

    def _git_recent_commits(self, rel_path: str, limit: int = 5) -> list[dict[str, str]]:
        result = self._run_git(
            [
                "log",
                "--follow",
                "--format=%H%x1f%cI%x1f%s",
                "-n",
                str(limit),
                "--",
                rel_path,
            ],
            check=False,
        )
        if result.returncode != 0:
            return []
        commits: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            sha, _, rest = line.partition("\x1f")
            committed_at, _, summary = rest.partition("\x1f")
            if not sha or not summary:
                continue
            commits.append(
                {
                    "sha": sha.strip(),
                    "committed_at": committed_at.strip(),
                    "summary": summary.strip(),
                }
            )
        return commits

    def _git_line_commit(self, rel_path: str, line_number: int) -> dict[str, str] | None:
        if rel_path not in self._git_file_blame_cache:
            result = self._run_git(["blame", "--line-porcelain", "--", rel_path], check=False)
            if result.returncode != 0:
                self._git_file_blame_cache[rel_path] = {}
            else:
                blame_data: dict[int, str] = {}
                current_sha = None
                for line in result.stdout.splitlines():
                    if not line:
                        continue
                    if current_sha is None:
                        current_sha = line.split(" ", 1)[0]
                    elif line.startswith("\t"):
                        # This line indicates the end of a porcelain block
                        current_sha = None
                    elif line.startswith("result-line "):
                        target_line = int(line.split(" ")[1])
                        if current_sha and set(current_sha) != {"0"}:
                            blame_data[target_line] = current_sha
                self._git_file_blame_cache[rel_path] = blame_data

        sha = self._git_file_blame_cache.get(rel_path, {}).get(line_number)
        if not sha:
            return None

        return self._git_commit_details(sha)

    def _git_commit_details(self, sha: str) -> dict[str, str]:
        cached = self._git_commit_detail_cache.get(sha)
        if cached is not None:
            return cached

        result = self._run_git(
            ["show", "-s", "--format=%H%x1f%cI%x1f%s", sha],
            check=False,
        )
        if result.returncode != 0:
            details = {"sha": sha, "committed_at": "", "summary": ""}
            self._git_commit_detail_cache[sha] = details
            return details

        raw = result.stdout.strip().splitlines()
        if not raw:
            details = {"sha": sha, "committed_at": "", "summary": ""}
            self._git_commit_detail_cache[sha] = details
            return details

        commit_sha, _, rest = raw[0].partition("\x1f")
        committed_at, _, summary = rest.partition("\x1f")
        details = {
            "sha": commit_sha.strip() or sha,
            "committed_at": committed_at.strip(),
            "summary": summary.strip(),
        }
        self._git_commit_detail_cache[sha] = details
        return details

    def _git_status(self, rel_path: str, *, tracked: bool) -> str:
        result = self._run_git(
            ["status", "--short", "--", rel_path],
            check=False,
        )
        if result.returncode != 0:
            return "tracked" if tracked else "untracked"
        raw_status = result.stdout.strip()
        if not raw_status:
            return "clean" if tracked else "untracked"
        status_code = raw_status[:2]
        if status_code == "??":
            return "untracked"
        if "R" in status_code:
            return "renamed"
        if "D" in status_code:
            return "deleted"
        if "A" in status_code:
            return "added"
        if "M" in status_code:
            return "modified"
        return "changed"

    @staticmethod
    def _node_line_number(node_metadata: dict[str, Any]) -> int | None:
        raw_line = node_metadata.get("line")
        if isinstance(raw_line, int):
            return raw_line
        if isinstance(raw_line, str) and raw_line.isdigit():
            return int(raw_line)
        return None

    @staticmethod
    def _history_subject(node_metadata: dict[str, Any]) -> str:
        for key in ("symbol", "route_path", "handler", "text"):
            value = node_metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _build_symbol_recent_commits(
        *,
        subject: str,
        line_commit: dict[str, str],
        file_recent_commits: Any,
    ) -> list[dict[str, str]]:
        commits: list[dict[str, str]] = []
        seen: set[str] = set()

        def add(commit: dict[str, str]) -> None:
            sha = str(commit.get("sha", "") or "")
            if not sha or sha in seen:
                return
            seen.add(sha)
            commits.append(commit)

        add(line_commit)
        normalized_subject = subject.lower().strip()
        if isinstance(file_recent_commits, list):
            for commit in file_recent_commits:
                if not isinstance(commit, dict):
                    continue
                summary = str(commit.get("summary", "") or "")
                if normalized_subject and normalized_subject in summary.lower():
                    add(
                        {
                            "sha": str(commit.get("sha", "") or ""),
                            "committed_at": str(commit.get("committed_at", "") or ""),
                            "summary": summary,
                        }
                    )
            for commit in file_recent_commits:
                if not isinstance(commit, dict) or len(commits) >= 3:
                    continue
                add(
                    {
                        "sha": str(commit.get("sha", "") or ""),
                        "committed_at": str(commit.get("committed_at", "") or ""),
                        "summary": str(commit.get("summary", "") or ""),
                    }
                )

        return commits[:5]

    @staticmethod
    def _build_symbol_history_summary(
        *,
        subject: str,
        status: str,
        line_commit: dict[str, str],
        recent_commits: list[dict[str, str]],
    ) -> str:
        subject_label = subject or "this node"
        prefix = f"Current state: {status}. " if status and status != "clean" else ""
        summary = line_commit.get("summary", "").strip()
        if not summary:
            return f"{prefix}No symbol-level git history available yet.".strip()

        trailing = [
            commit.get("summary", "").strip()
            for commit in recent_commits[1:3]
            if commit.get("summary")
        ]
        if trailing:
            return f"{prefix}Last touch for {subject_label}: {summary}. Related changes: {'; '.join(trailing)}".strip()
        return f"{prefix}Last touch for {subject_label}: {summary}.".strip()

    @staticmethod
    def _build_history_summary(recent_commits: list[dict[str, str]], status: str) -> str:
        if not recent_commits:
            if status == "untracked":
                return "New file not committed yet."
            return "No git history available for this node yet."
        summaries = [commit.get("summary", "").strip() for commit in recent_commits if commit.get("summary")]
        compact = "; ".join(summaries[:3])
        prefix = f"Current state: {status}. " if status and status != "clean" else ""
        return f"{prefix}Recent changes: {compact}".strip()

    @staticmethod
    def _extract_imports(file_path: Path) -> list[str]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        suffix = file_path.suffix.lower()
        if suffix in _PYTHON_SUFFIXES:
            try:
                tree = ast.parse(source, filename=str(file_path))
            except (SyntaxError, ValueError):
                return []
            python_modules: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        python_modules.add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    python_modules.add(node.module)
            return sorted(python_modules)

        modules: set[str] = set()
        if suffix in {".ts", ".tsx", ".js", ".jsx"}:
            for match in re.finditer(r"import\s+(?:[^;]*?from\s+)?['\"]([^'\"]+)['\"]", source):
                modules.add(match.group(1))
            for match in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", source):
                modules.add(match.group(1))
        elif suffix == ".java":
            for match in re.finditer(r"^\s*import\s+([\w.]+);", source, flags=re.MULTILINE):
                modules.add(match.group(1))
        elif suffix == ".go":
            for match in re.finditer(r'"([^"]+)"', source):
                modules.add(match.group(1))
        elif suffix == ".rs":
            for match in re.finditer(r"^\s*use\s+([\w:]+)", source, flags=re.MULTILINE):
                modules.add(match.group(1))
        return sorted(modules)

    @classmethod
    def _extract_python_metadata(
        cls,
        file_path: Path,
        rel_path: str,
    ) -> tuple[list[_NodeSpec], list[_EdgeSpec]]:
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, ValueError):
            return cls._extract_todo_nodes(source if "source" in locals() else "", rel_path), []

        nodes: list[_NodeSpec] = cls._extract_todo_nodes(source, rel_path)
        edges: list[_EdgeSpec] = []

        class MetadataVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.class_stack: list[tuple[str, str]] = []
                self.http_aliases: set[str] = set()

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    alias_name = alias.asname or alias.name.split(".")[0]
                    if alias.name.split(".")[0] in {"httpx", "requests"}:
                        self.http_aliases.add(alias_name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                module = node.module or ""
                for alias in node.names:
                    alias_name = alias.asname or alias.name
                    if module.split(".")[0] in {"httpx", "requests"}:
                        self.http_aliases.add(alias_name)
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                class_type = cls._class_node_type(node)
                class_name = cls._qualified_symbol_name(rel_path, node.name, self.class_stack)
                nodes.append(_NodeSpec(class_type, class_name, {
                    "path": rel_path,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "symbol": node.name,
                }))
                edges.append(_EdgeSpec("file", rel_path, class_type, class_name, "contains"))
                if cls._is_controller_class(node):
                    nodes.append(_NodeSpec("controller", class_name, {"path": rel_path, "line": node.lineno, "symbol": node.name}))
                    edges.append(_EdgeSpec(class_type, class_name, "controller", class_name, "tracks"))

                self.class_stack.append((class_type, class_name))
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._visit_function_like(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._visit_function_like(node)

            def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                function_name = cls._qualified_symbol_name(rel_path, node.name, self.class_stack)
                nodes.append(_NodeSpec("function", function_name, {
                    "path": rel_path,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "symbol": node.name,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }))
                owner_type = self.class_stack[-1][0] if self.class_stack else "file"
                owner_name = self.class_stack[-1][1] if self.class_stack else rel_path
                edges.append(_EdgeSpec(owner_type, owner_name, "function", function_name, "contains"))

                route_info = cls._route_info(node)
                if route_info is not None:
                    method, path = route_info
                    route_name = f"{method} {path}"
                    nodes.append(_NodeSpec("route", route_name, {
                        "path": rel_path,
                        "method": method,
                        "route_path": path,
                        "line": node.lineno,
                        "handler": function_name,
                    }))
                    route_source_type = "controller" if self.class_stack else "function"
                    route_source_name = self.class_stack[-1][1] if self.class_stack else function_name
                    edges.append(_EdgeSpec(route_source_type, route_source_name, "route", route_name, "exposes_route"))

                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue
                    external_call = cls._external_service_from_call(child, self.http_aliases)
                    if external_call is not None:
                        nodes.append(_NodeSpec("external_service_api", external_call, {
                            "path": rel_path,
                            "line": getattr(child, "lineno", node.lineno),
                            "caller": function_name,
                        }))
                        edges.append(_EdgeSpec("function", function_name, "external_service_api", external_call, "uses_external_service"))

                    mq_info = cls._mq_topic_from_call(child)
                    if mq_info is not None:
                        relation, topic_name = mq_info
                        nodes.append(_NodeSpec("mq_topic", topic_name, {"path": rel_path, "line": getattr(child, "lineno", node.lineno)}))
                        edges.append(_EdgeSpec("function", function_name, "mq_topic", topic_name, relation))

                self.generic_visit(node)

        MetadataVisitor().visit(tree)
        return cls._dedupe_node_specs(nodes), cls._dedupe_edge_specs(edges)

    @classmethod
    def _extract_script_metadata(
        cls,
        source: str,
        rel_path: str,
    ) -> tuple[dict[str, Any], list[_NodeSpec], list[_EdgeSpec]]:
        nodes: list[_NodeSpec] = []
        edges: list[_EdgeSpec] = []
        symbol_count = 0
        route_count = 0
        external_services: set[str] = set()
        mq_topics: set[str] = set()

        for match in re.finditer(r"(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)|\btrait\s+([A-Za-z_][A-Za-z0-9_]*)", source):
            name = match.group(1) or match.group(2)
            symbol_name = f"{rel_path}::{name}"
            nodes.append(_NodeSpec("interface", symbol_name, {"path": rel_path, "line": _line_number(source, match.start()), "symbol": name}))
            edges.append(_EdgeSpec("file", rel_path, "interface", symbol_name, "contains"))
            symbol_count += 1

        for match in re.finditer(r"(?:export\s+)?(abstract\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)|\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)", source):
            is_abstract = bool(match.group(1))
            name = match.group(2) or match.group(3)
            symbol_name = f"{rel_path}::{name}"
            node_type = "abstract_class" if is_abstract else "class"
            line = _line_number(source, match.start())
            nodes.append(_NodeSpec(node_type, symbol_name, {"path": rel_path, "line": line, "symbol": name}))
            edges.append(_EdgeSpec("file", rel_path, node_type, symbol_name, "contains"))
            if name.endswith("Controller"):
                nodes.append(_NodeSpec("controller", symbol_name, {"path": rel_path, "line": line, "symbol": name}))
                edges.append(_EdgeSpec(node_type, symbol_name, "controller", symbol_name, "tracks"))
            symbol_count += 1

        patterns = [
            r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(",
            r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                name = match.group(1)
                symbol_name = f"{rel_path}::{name}"
                nodes.append(_NodeSpec("function", symbol_name, {"path": rel_path, "line": _line_number(source, match.start()), "symbol": name}))
                edges.append(_EdgeSpec("file", rel_path, "function", symbol_name, "contains"))
                symbol_count += 1

        # --- HTTP route detection (Express/Fastify/Koa patterns) ---
        for match in re.finditer(
            r"(?:router|app|server)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
            source,
        ):
            method = match.group(1).upper()
            path = match.group(2)
            route_name = f"{method} {path}"
            nodes.append(_NodeSpec("route", route_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "method": method, "route_path": path, "framework": "express",
            }))
            edges.append(_EdgeSpec("file", rel_path, "route", route_name, "exposes_route"))
            route_count += 1

        # --- NestJS @Get/@Post etc. ---
        # Detect controller prefix for full path reconstruction
        controller_prefix = ""
        ctrl_match = _NESTJS_CONTROLLER_PATTERN.search(source)
        if ctrl_match:
            controller_prefix = ctrl_match.group(1).rstrip("/")

        for match in _NESTJS_ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            sub_path = (match.group(2) or "").strip("/")
            full_path = f"/{controller_prefix}/{sub_path}".replace("//", "/").rstrip("/") or "/"
            route_name = f"{method} {full_path}"
            nodes.append(_NodeSpec("api_endpoint", route_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "method": method, "route_path": full_path, "framework": "nestjs",
            }))
            edges.append(_EdgeSpec("file", rel_path, "api_endpoint", route_name, "exposes_route"))
            route_count += 1

        # --- Spring Boot @GetMapping / @PostMapping etc. ---
        for match in _SPRING_ROUTE_PATTERN.finditer(source):
            annotation = match.group(1)
            route_path = match.group(2)
            method_map = {
                "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
                "PatchMapping": "PATCH", "DeleteMapping": "DELETE", "RequestMapping": "ANY",
            }
            method = method_map.get(annotation, "ANY")
            route_name = f"{method} {route_path}"
            nodes.append(_NodeSpec("api_endpoint", route_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "method": method, "route_path": route_path, "framework": "spring",
            }))
            edges.append(_EdgeSpec("file", rel_path, "api_endpoint", route_name, "exposes_route"))
            route_count += 1

        # --- Go Gin/Fiber/Chi route patterns ---
        for match in _GO_ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            route_path = match.group(2)
            route_name = f"{method} {route_path}"
            nodes.append(_NodeSpec("api_endpoint", route_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "method": method, "route_path": route_path, "framework": "gin",
            }))
            edges.append(_EdgeSpec("file", rel_path, "api_endpoint", route_name, "exposes_route"))
            route_count += 1

        # --- Rust axum/actix-web route attributes ---
        for match in _RUST_ROUTE_ATTR_PATTERN.finditer(source):
            route_path = match.group(1)
            # Infer method from attribute name (e.g. #[get("/")] → GET)
            attr_line = source[max(0, match.start() - 5):match.start() + 30]
            method = "GET"
            for m in ("post", "put", "patch", "delete"):
                if m in attr_line:
                    method = m.upper()
                    break
            route_name = f"{method} {route_path}"
            nodes.append(_NodeSpec("api_endpoint", route_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "method": method, "route_path": route_path, "framework": "axum",
            }))
            edges.append(_EdgeSpec("file", rel_path, "api_endpoint", route_name, "exposes_route"))
            route_count += 1

        # --- WebSocket: NestJS @WebSocketGateway + @SubscribeMessage ---
        ws_gateway_path = ""
        gw_match = _WS_GATEWAY_PATTERN.search(source)
        if gw_match:
            ws_gateway_path = gw_match.group(1) or ""
            nodes.append(_NodeSpec("websocket_endpoint", f"WS {ws_gateway_path or '/'}", {
                "path": rel_path, "line": _line_number(source, gw_match.start()),
                "gateway_path": ws_gateway_path, "framework": "nestjs",
            }))
            edges.append(_EdgeSpec("file", rel_path, "websocket_endpoint", f"WS {ws_gateway_path or '/'}", "exposes_websocket"))

        for match in _WS_SUBSCRIBE_PATTERN.finditer(source):
            event_name = match.group(1)
            ws_endpoint_name = f"WS:{event_name}"
            nodes.append(_NodeSpec("websocket_endpoint", ws_endpoint_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "event": event_name, "framework": "nestjs",
            }))
            edges.append(_EdgeSpec("file", rel_path, "websocket_endpoint", ws_endpoint_name, "websocket"))

        # --- Spring WebSocket @MessageMapping ---
        for match in _SPRING_WS_MAPPING_PATTERN.finditer(source):
            dest = match.group(1)
            ws_endpoint_name = f"WS:{dest}"
            nodes.append(_NodeSpec("websocket_endpoint", ws_endpoint_name, {
                "path": rel_path, "line": _line_number(source, match.start()),
                "event": dest, "framework": "spring",
            }))
            edges.append(_EdgeSpec("file", rel_path, "websocket_endpoint", ws_endpoint_name, "websocket"))

        # --- External service calls (URL literals) ---
        for match in _URL_PATTERN.finditer(source):
            url = match.group(0)
            external_services.add(url)
            nodes.append(_NodeSpec("external_service_api", url, {
                "path": rel_path, "line": _line_number(source, match.start()),
            }))
            edges.append(_EdgeSpec("file", rel_path, "external_service_api", url, "uses_external_service"))

        # --- Message queue: publish / consume calls ---
        for action in _MQ_PUBLISH_CALLS.union(_MQ_CONSUME_CALLS):
            for match in re.finditer(rf"\.{action}\s*\(\s*['\"]([^'\"]+)['\"]", source):
                topic_name = match.group(1)
                relation = "publishes" if action in _MQ_PUBLISH_CALLS else "consumes"
                node_type = "mq_producer" if action in _MQ_PUBLISH_CALLS else "mq_consumer"
                mq_topics.add(topic_name)
                nodes.append(_NodeSpec("mq_topic", topic_name, {
                    "path": rel_path, "line": _line_number(source, match.start()),
                }))
                nodes.append(_NodeSpec(node_type, f"{node_type}:{topic_name}", {
                    "path": rel_path, "line": _line_number(source, match.start()),
                    "topic": topic_name,
                }))
                edges.append(_EdgeSpec("file", rel_path, node_type, f"{node_type}:{topic_name}", relation))
                edges.append(_EdgeSpec(node_type, f"{node_type}:{topic_name}", "mq_topic", topic_name, relation))

        return {
            "symbol_count": symbol_count,
            "route_count": route_count,
            "external_service_count": len(external_services),
            "mq_topic_count": len(mq_topics),
        }, cls._dedupe_node_specs(nodes), cls._dedupe_edge_specs(edges)

    @staticmethod
    def _extract_markdown_metadata(source: str) -> dict[str, Any]:
        headings = [match.group(2).strip() for match in _MARKDOWN_HEADING_PATTERN.finditer(source)]
        return {
            "heading_count": len(headings),
            "headings": headings[:20],
            "link_count": len(_URL_PATTERN.findall(source)),
        }

    @staticmethod
    def _extract_markdown_task_nodes(source: str, rel_path: str) -> list[_NodeSpec]:
        nodes: list[_NodeSpec] = []
        for index, line in enumerate(source.splitlines(), start=1):
            match = _MARKDOWN_TASK_PATTERN.match(line)
            if match is None:
                continue
            nodes.append(_NodeSpec("todo", f"{rel_path}::TODO:{index}", {"path": rel_path, "line": index, "text": match.group(1).strip()}))
        return nodes

    @staticmethod
    def _extract_structured_metadata(source: str, suffix: str) -> dict[str, Any]:
        keys: list[str] = []
        if suffix == ".json":
            try:
                parsed = json.loads(source)
                if isinstance(parsed, dict):
                    keys = sorted(str(key) for key in parsed.keys())
            except json.JSONDecodeError:
                keys = []
        elif suffix == ".toml":
            try:
                parsed = tomllib.loads(source)
                if isinstance(parsed, dict):
                    keys = sorted(str(key) for key in parsed.keys())
            except tomllib.TOMLDecodeError:
                keys = []
        else:
            keys = sorted({match.group(1) for match in _YAML_KEY_PATTERN.finditer(source)})
            if not keys:
                keys = sorted({match.group(1) for match in _INI_KEY_PATTERN.finditer(source)})
        return {"top_level_keys": keys[:50], "top_level_key_count": len(keys)}

    @staticmethod
    def _extract_todo_nodes(source: str, rel_path: str) -> list[_NodeSpec]:
        nodes: list[_NodeSpec] = []
        for index, line in enumerate(source.splitlines(), start=1):
            match = _TODO_PATTERN.search(line)
            if match is None:
                continue
            text = (match.group(1) or "").strip() or "TODO"
            nodes.append(_NodeSpec("todo", f"{rel_path}::TODO:{index}", {"path": rel_path, "line": index, "text": text}))
        return nodes

    @staticmethod
    def _qualified_symbol_name(rel_path: str, symbol_name: str, class_stack: list[tuple[str, str]]) -> str:
        if not class_stack:
            return f"{rel_path}::{symbol_name}"
        owner_name = class_stack[-1][1].split("::", 1)[1]
        return f"{rel_path}::{owner_name}.{symbol_name}"

    @staticmethod
    def _class_node_type(node: ast.ClassDef) -> str:
        base_names = {RepoScanner._base_name(base) for base in node.bases}
        has_abstract_method = any(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(RepoScanner._base_name(dec) == "abstractmethod" for dec in child.decorator_list)
            for child in node.body
        )
        if "Protocol" in base_names:
            return "interface"
        if "ABC" in base_names or "ABCMeta" in base_names or has_abstract_method:
            return "abstract_class"
        return "class"

    @staticmethod
    def _is_controller_class(node: ast.ClassDef) -> bool:
        if node.name.endswith("Controller"):
            return True
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and RepoScanner._route_info(child) is not None:
                return True
        return False

    @staticmethod
    def _route_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method_name = decorator.func.attr.lower()
            if method_name not in _HTTP_ROUTE_DECORATORS:
                continue
            route_path = RepoScanner._string_arg_value(decorator.args)
            if route_path is None:
                continue
            method = RepoScanner._route_methods_from_keywords(decorator.keywords) if method_name == "route" else method_name.upper()
            return method, route_path
        return None

    @staticmethod
    def _route_methods_from_keywords(keywords: list[ast.keyword]) -> str:
        for keyword in keywords:
            if keyword.arg != "methods" or not isinstance(keyword.value, (ast.List, ast.Tuple)):
                continue
            methods = [elt.value.upper() for elt in keyword.value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
            if methods:
                return "/".join(methods)
        return "ROUTE"

    @staticmethod
    def _string_arg_value(args: list[ast.expr]) -> str | None:
        if not args:
            return None
        first = args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None

    @staticmethod
    def _external_service_from_call(call: ast.Call, http_aliases: set[str]) -> str | None:
        func = call.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in http_aliases and func.attr.lower() in _HTTP_ROUTE_DECORATORS.union({"request"}):
                return RepoScanner._extract_url_from_call(call)
        if isinstance(func, ast.Name) and func.id in http_aliases:
            return RepoScanner._extract_url_from_call(call)
        return None

    @staticmethod
    def _extract_url_from_call(call: ast.Call) -> str | None:
        for candidate in [*call.args, *(kw.value for kw in call.keywords if kw.arg == "url")]:
            if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str) and _URL_PATTERN.match(candidate.value):
                return candidate.value
        return None

    @staticmethod
    def _mq_topic_from_call(call: ast.Call) -> tuple[str, str] | None:
        func = call.func
        if not isinstance(func, ast.Attribute):
            return None
        action = func.attr.lower()
        if action in _MQ_PUBLISH_CALLS:
            relation = "publishes"
        elif action in _MQ_CONSUME_CALLS:
            relation = "consumes"
        else:
            return None
        topic_name = RepoScanner._string_arg_value(call.args)
        if topic_name is None:
            return None
        return relation, topic_name

    @staticmethod
    def _base_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Subscript):
            return RepoScanner._base_name(node.value)
        return ""

    @staticmethod
    def _dedupe_node_specs(nodes: list[_NodeSpec]) -> list[_NodeSpec]:
        deduped: dict[tuple[str, str], _NodeSpec] = {}
        for node in nodes:
            key = (node.node_type, node.name)
            existing = deduped.get(key)
            deduped[key] = node if existing is None else _NodeSpec(node.node_type, node.name, {**existing.metadata, **node.metadata})
        return list(deduped.values())

    @staticmethod
    def _dedupe_edge_specs(edges: list[_EdgeSpec]) -> list[_EdgeSpec]:
        deduped: dict[tuple[str, str, str, str, str], _EdgeSpec] = {}
        for edge in edges:
            deduped[(edge.source_type, edge.source_name, edge.target_type, edge.target_name, edge.relation)] = edge
        return list(deduped.values())


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1
