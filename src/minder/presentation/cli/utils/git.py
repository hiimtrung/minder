from __future__ import annotations

import configparser
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def run_git(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=check,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Git executable not found. Please install git to support this command."
        ) from None


def repo_root(path: str = ".") -> Path:
    result = run_git(["rev-parse", "--show-toplevel"], cwd=path)
    return Path(result.stdout.strip()).resolve()


def git_branch(repo_root_path: Path) -> str | None:
    result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root_path)
    branch = result.stdout.strip()
    return branch or None


def git_remote_url(repo_root_path: Path) -> str | None:
    result = run_git(
        ["config", "--get", "remote.origin.url"],
        cwd=repo_root_path,
        check=False,
    )
    remote_url = result.stdout.strip()
    return remote_url or None


def normalize_repo_remote(remote_url: str | None) -> str | None:
    if remote_url is None:
        return None
    raw_url = remote_url.strip()
    if not raw_url:
        return None
    if raw_url.startswith("git@"):
        host_and_path = raw_url[4:]
        host, separator, path = host_and_path.partition(":")
        if separator and host and path:
            normalized_path = path.strip().lstrip("/").removesuffix(".git")
            if normalized_path:
                return f"git@{host}:{normalized_path}.git"
        return raw_url
    if (
        raw_url.startswith("ssh://")
        or raw_url.startswith("http://")
        or raw_url.startswith("https://")
    ):
        parts = urlsplit(raw_url)
        host = parts.hostname or ""
        path = parts.path.strip().lstrip("/").removesuffix(".git")
        user = parts.username or "git"
        if host and path:
            return f"{user}@{host}:{path}.git"
    return raw_url.rstrip("/")


def repo_name_from_remote(remote_url: str | None) -> str | None:
    normalized_remote = normalize_repo_remote(remote_url)
    if not normalized_remote:
        return None
    _, _, path = normalized_remote.partition(":")
    repo_name = path.rsplit("/", 1)[-1].removesuffix(".git").strip()
    return repo_name or None


def git_file_delta(
    repo_root_path: Path, diff_base: str | None = None
) -> tuple[list[str] | None, list[str]]:
    diff_command = ["diff", "--name-only", "--diff-filter=ACMRD"]
    if diff_base:
        diff_command.append(f"{diff_base}...HEAD")
    else:
        diff_command.append("HEAD")
    diff_result = run_git(diff_command, cwd=repo_root_path)
    changed = {line.strip() for line in diff_result.stdout.splitlines() if line.strip()}

    deleted_result = run_git(
        [
            "diff",
            "--name-only",
            "--diff-filter=D",
            *([f"{diff_base}...HEAD"] if diff_base else ["HEAD"]),
        ],
        cwd=repo_root_path,
    )
    deleted = {
        line.strip() for line in deleted_result.stdout.splitlines() if line.strip()
    }
    changed.difference_update(deleted)

    untracked_result = run_git(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=repo_root_path,
    )
    changed.update(
        line.strip() for line in untracked_result.stdout.splitlines() if line.strip()
    )
    if diff_base is None:
        return None, sorted(deleted)
    return sorted(changed), sorted(deleted)


def gitmodules_submodule_sections(gitmodules_path: Path) -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(gitmodules_path.read_text(encoding="utf-8"))
    except (configparser.Error, OSError):
        return {}

    submodules: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        stripped = section.strip()
        if not stripped.lower().startswith("submodule"):
            continue
        _, _, quoted = stripped.partition(" ")
        name = quoted.strip().strip('"').strip()
        if not name:
            continue
        fields = {key: parser.get(section, key) for key in parser.options(section)}
        submodules[name] = fields
    return submodules


def submodule_branch_relationships(
    repo_root_path: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    gitmodules = repo_root_path / ".gitmodules"
    if not gitmodules.is_file():
        return []

    sections = gitmodules_submodule_sections(gitmodules)
    relationships: list[dict[str, Any]] = []
    for name, fields in sections.items():
        url = (fields.get("url") or "").strip()
        if not url:
            continue
        target_branch = (fields.get("branch") or "").strip() or "main"
        submodule_path = (fields.get("path") or name).strip()
        target_repo_name = (
            repo_name_from_remote(url) or name.rsplit("/", 1)[-1].strip() or name
        )
        relationships.append(
            {
                "source_branch": source_branch,
                "target_repo_name": target_repo_name,
                "target_repo_url": normalize_repo_remote(url),
                "target_branch": target_branch,
                "relation": "depends_on",
                "direction": "outbound",
                "confidence": 1.0,
                "metadata": {
                    "discovered_by": "minder-cli",
                    "source": "gitmodules",
                    "submodule_path": submodule_path,
                    "submodule_name": name,
                },
            }
        )
    return relationships


def normalize_relationship_entry(
    entry: dict[str, Any], *, fallback_branch: str | None
) -> dict[str, Any] | None:
    target_repo_name = str(entry.get("target_repo_name") or "").strip()
    target_branch = str(entry.get("target_branch") or "").strip()
    if not target_repo_name or not target_branch:
        return None

    raw_source_branch = entry.get("source_branch")
    source_branch = str(raw_source_branch or fallback_branch or "").strip() or None

    raw_url = entry.get("target_repo_url")
    target_repo_url = (
        normalize_repo_remote(raw_url) if isinstance(raw_url, str) else None
    )

    raw_id = entry.get("target_repo_id")
    target_repo_id = (
        raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None
    )

    direction = str(entry.get("direction") or "outbound").strip() or "outbound"
    allowed_directions = ("outbound", "inbound", "bidirectional")
    if direction not in allowed_directions:
        direction = "outbound"

    try:
        confidence = float(entry.get("confidence", 1.0))
    except (TypeError, ValueError):
        confidence = 1.0

    raw_metadata = entry.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    metadata.setdefault("discovered_by", "minder-cli")

    relation = str(entry.get("relation") or "depends_on").strip() or "depends_on"

    normalized: dict[str, Any] = {
        "source_branch": source_branch,
        "target_repo_name": target_repo_name,
        "target_repo_url": target_repo_url,
        "target_branch": target_branch,
        "relation": relation,
        "direction": direction,
        "confidence": confidence,
        "metadata": metadata,
    }
    if target_repo_id:
        normalized["target_repo_id"] = target_repo_id
    return normalized


def branch_topology_override_relationships(
    repo_root_path: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    override_path = repo_root_path / ".minder" / "branch-topology.toml"
    if not override_path.is_file():
        return []
    try:
        data = tomllib.loads(override_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []

    raw_entries = data.get("branch_relationships")
    if not isinstance(raw_entries, list):
        return []

    relationships: list[dict[str, Any]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_relationship_entry(raw, fallback_branch=source_branch)
        if normalized:
            normalized["metadata"]["source"] = "branch-topology.toml"
            relationships.append(normalized)
    return relationships


def dedupe_branch_relationships(
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    for rel in relationships:
        key = (
            rel["source_branch"],
            rel["target_repo_name"],
            rel["target_branch"],
        )
        if key not in seen:
            seen[key] = rel
        else:
            # Merge metadata, the earlier one in the list (overrides) wins if there's a conflict
            new_metadata = rel["metadata"].copy()
            new_metadata.update(seen[key]["metadata"])
            seen[key]["metadata"] = new_metadata
    return list(seen.values())


def detect_branch_relationships(
    repo_root_path: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    relationships = submodule_branch_relationships(repo_root_path, source_branch)
    overrides = branch_topology_override_relationships(repo_root_path, source_branch)
    return dedupe_branch_relationships(overrides + relationships)
