from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from getpass import getpass
from importlib.metadata import (
    PackageNotFoundError,
    metadata as package_metadata,
    version as package_version,
)
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from minder.tools.repo_scanner import RepoScanner

_DEFAULT_SERVER_URL = "http://localhost:8801/sse"
_DEFAULT_PROTOCOL = "sse"
_LOCAL_MCP_TARGETS = ("vscode", "cursor", "claude-code")
_PYPI_JSON_URL = "https://pypi.org/pypi/minder/json"
_IDE_GITIGNORE_KEY = "minder-ide-bootstrap"
_DEFAULT_RELEASE_REPOSITORY_URL = "https://github.com/hiimtrung/minder"
_GITHUB_RELEASE_REPOSITORY_API = "https://api.github.com/repos"
_SERVER_RELEASE_METADATA_NAME = ".minder-release.json"


def _bootstrap_version() -> str:
    return _installed_package_version() or "dev"


def _client_config_path() -> Path:
    return Path.home() / ".minder" / "client.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _marker_pair(path: Path, key: str) -> tuple[str, str]:
    if path.name == ".gitignore":
        return (f"# minder:begin {key}", f"# minder:end {key}")
    return (f"<!-- minder:begin {key} -->", f"<!-- minder:end {key} -->")


def _wrap_managed_block(path: Path, key: str, body: str) -> str:
    start, end = _marker_pair(path, key)
    normalized_body = body.strip("\n")
    return f"{start}\n{normalized_body}\n{end}\n"


def _upsert_managed_block(path: Path, key: str, body: str) -> None:
    block = _wrap_managed_block(path, key, body)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    start, end = _marker_pair(path, key)
    if start in existing and end in existing:
        before, remainder = existing.split(start, 1)
        _, after = remainder.split(end, 1)
        updated = before.rstrip()
        if updated:
            updated += "\n\n"
        updated += block.rstrip("\n")
        tail = after.strip("\n")
        if tail:
            updated += "\n\n" + tail
        updated += "\n"
    else:
        updated = existing.rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def _remove_managed_block(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    existing = path.read_text(encoding="utf-8")
    start, end = _marker_pair(path, key)
    if start not in existing or end not in existing:
        return False
    before, remainder = existing.split(start, 1)
    _, after = remainder.split(end, 1)
    updated = before.rstrip("\n")
    tail = after.strip("\n")
    if updated and tail:
        updated = f"{updated}\n\n{tail}\n"
    elif updated:
        updated = f"{updated}\n"
    elif tail:
        updated = f"{tail}\n"
    else:
        updated = ""
    if updated:
        path.write_text(updated, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return True


def _prompt_client_key() -> str:
    client_key = getpass("Minder client key (mkc_...): ").strip()
    if not client_key:
        raise ValueError("Client key is required")
    return client_key


def _prompt_protocol(default: str = _DEFAULT_PROTOCOL) -> str:
    value = input(f"Minder protocol [sse/stdio] (default: {default}): ").strip().lower()
    return value or default


def _normalize_protocol(raw_protocol: str | None) -> str:
    protocol = (raw_protocol or "").strip().lower() or _DEFAULT_PROTOCOL
    if protocol not in {"sse", "stdio"}:
        raise ValueError("Protocol must be either 'sse' or 'stdio'")
    return protocol


def _require_client_settings(config_path: Path) -> dict[str, Any]:
    payload = _load_json(config_path)
    protocol = _normalize_protocol(str(payload.get("protocol", _DEFAULT_PROTOCOL)))
    client_key = str(payload.get("client_api_key", "")).strip()
    server_url = str(payload.get("server_url", "")).strip()
    if not client_key:
        raise ValueError(f"No client_api_key found in {config_path}")
    if protocol == "sse" and not server_url:
        raise ValueError(f"No server_url found in {config_path}")
    payload["protocol"] = protocol
    return payload


def _parse_version(raw_version: str) -> tuple[int, ...]:
    normalized = raw_version.strip().lstrip("v")
    parts: list[int] = []
    for piece in normalized.split("."):
        digits = "".join(char for char in piece if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _installed_package_version() -> str | None:
    try:
        return package_version("minder")
    except PackageNotFoundError:
        return None


def _latest_pypi_version() -> str | None:
    try:
        response = httpx.get(_PYPI_JSON_URL, timeout=3)
        response.raise_for_status()
    except Exception:
        return None
    payload = response.json()
    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    version_value = info.get("version")
    if not isinstance(version_value, str) or not version_value.strip():
        return None
    return version_value.strip()


def _maybe_print_upgrade_notice() -> None:
    installed = _installed_package_version()
    latest = _latest_pypi_version()
    if installed is None or latest is None:
        return
    if _parse_version(latest) <= _parse_version(installed):
        return
    print(
        f"A newer minder CLI is available ({installed} -> {latest}). "
        "Run 'uv tool upgrade minder' or 'pipx upgrade minder'."
    )


def _project_repository_url() -> str:
    override = os.getenv("MINDER_RELEASE_REPOSITORY", "").strip()
    if override:
        if override.startswith("http://") or override.startswith("https://"):
            return override
        return f"https://github.com/{override.strip('/')}"
    try:
        metadata = package_metadata("minder")
    except PackageNotFoundError:
        return _DEFAULT_RELEASE_REPOSITORY_URL
    for value in metadata.get_all("Project-URL") or []:
        label, _, url = value.partition(",")
        if label.strip().lower() == "repository" and url.strip():
            return url.strip()
    homepage = str(metadata.get("Home-page", "")).strip()
    return homepage or _DEFAULT_RELEASE_REPOSITORY_URL


def _project_repository_slug() -> str:
    repository_url = _project_repository_url().strip().rstrip("/")
    if repository_url.startswith("http://") or repository_url.startswith("https://"):
        parts = urlsplit(repository_url)
        path_parts = [piece for piece in parts.path.strip("/").split("/") if piece]
    else:
        path_parts = [piece for piece in repository_url.strip("/").split("/") if piece]
    if len(path_parts) < 2:
        raise ValueError(
            f"Unsupported repository URL for release lookup: {repository_url}"
        )
    return f"{path_parts[0]}/{path_parts[1].removesuffix('.git')}"


def _latest_github_release(repository_slug: str) -> dict[str, str] | None:
    try:
        response = httpx.get(
            f"{_GITHUB_RELEASE_REPOSITORY_API}/{repository_slug}/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
    except Exception:
        return None
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    tag_name = payload.get("tag_name")
    html_url = payload.get("html_url")
    if not isinstance(tag_name, str) or not tag_name.strip():
        return None
    if not isinstance(html_url, str) or not html_url.strip():
        html_url = f"https://github.com/{repository_slug}/releases/latest"
    return {"version": tag_name.strip(), "url": html_url.strip()}


def _default_server_install_dir() -> Path:
    current_link = Path.home() / ".minder" / "current"
    if current_link.exists():
        return current_link.resolve()
    releases_dir = Path.home() / ".minder" / "releases"
    if releases_dir.is_dir():
        candidates = [path for path in releases_dir.iterdir() if path.is_dir()]
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    return current_link


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        raw_line = line.strip()
        if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
            continue
        key, _, value = raw_line.partition("=")
        payload[key.strip()] = value.strip()
    return payload


def _server_release_metadata_path(install_dir: Path) -> Path:
    return install_dir / _SERVER_RELEASE_METADATA_NAME


def _load_server_release_metadata(install_dir: Path) -> dict[str, Any]:
    path = _server_release_metadata_path(install_dir)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _image_tag(image_ref: str | None) -> str | None:
    if image_ref is None:
        return None
    _, separator, tag = image_ref.rpartition(":")
    if not separator or not tag.strip():
        return None
    return tag.strip()


def _server_repository_slug(install_dir: Path) -> str:
    metadata = _load_server_release_metadata(install_dir)
    repository = metadata.get("repository")
    if isinstance(repository, str) and repository.strip():
        repository_url = repository.strip()
        if repository_url.startswith("http://") or repository_url.startswith(
            "https://"
        ):
            parts = urlsplit(repository_url)
            pieces = [piece for piece in parts.path.strip("/").split("/") if piece]
        else:
            pieces = [piece for piece in repository_url.strip("/").split("/") if piece]
        if len(pieces) >= 2:
            return f"{pieces[0]}/{pieces[1].removesuffix('.git')}"
    repo_owner = str(metadata.get("repo_owner", "")).strip()
    repo_name = str(metadata.get("repo_name", "")).strip()
    if repo_owner and repo_name:
        return f"{repo_owner}/{repo_name.removesuffix('.git')}"
    return _project_repository_slug()


def _server_current_version(install_dir: Path) -> str | None:
    metadata = _load_server_release_metadata(install_dir)
    release_tag = metadata.get("release_tag")
    if isinstance(release_tag, str) and release_tag.strip():
        return release_tag.strip()
    env_payload = _load_env_file(install_dir / ".env")
    return _image_tag(env_payload.get("MINDER_API_IMAGE")) or _image_tag(
        env_payload.get("MINDER_DASHBOARD_IMAGE")
    )


def _cli_update_available() -> tuple[str | None, str | None, bool]:
    installed = _installed_package_version()
    latest = _latest_pypi_version()
    if installed is None or latest is None:
        return installed, latest, False
    return installed, latest, _parse_version(latest) > _parse_version(installed)


def _server_update_available(
    install_dir: Path,
) -> tuple[str | None, str | None, str, str | None, bool]:
    repository_slug = _server_repository_slug(install_dir)
    current = _server_current_version(install_dir)
    latest_release = _latest_github_release(repository_slug)
    latest = latest_release["version"] if latest_release is not None else None
    release_url = latest_release["url"] if latest_release is not None else None
    if current is None or latest is None:
        return current, latest, repository_slug, release_url, False
    return (
        current,
        latest,
        repository_slug,
        release_url,
        _parse_version(latest) > _parse_version(current),
    )


def _print_cli_update_status() -> None:
    installed, latest, has_update = _cli_update_available()
    status = (
        f"update available ({installed} -> {latest})"
        if has_update and installed and latest
        else (
            "up to date"
            if installed and latest
            else "unable to determine latest version"
        )
    )
    print("CLI update status:")
    print(f"  installed: {installed or 'unknown'}")
    print(f"  latest: {latest or 'unknown'}")
    print(f"  status: {status}")


def _print_server_update_status(install_dir: Path) -> None:
    if not install_dir.is_dir():
        print("Server update status:")
        print(f"  install dir: {install_dir}")
        print("  status: no local release installation found")
        return
    current, latest, repository_slug, release_url, has_update = (
        _server_update_available(install_dir)
    )
    status = (
        f"update available ({current} -> {latest})"
        if has_update and current and latest
        else (
            "up to date" if current and latest else "unable to determine latest release"
        )
    )
    print("Server update status:")
    print(f"  install dir: {install_dir}")
    print(f"  repository: {repository_slug}")
    print(f"  current: {current or 'unknown'}")
    print(f"  latest: {latest or 'unknown'}")
    if release_url:
        print(f"  release: {release_url}")
    print(f"  status: {status}")


def _cli_update_commands(manager: str) -> list[list[str]]:
    if manager == "uv":
        return [["uv", "tool", "upgrade", "minder"]]
    if manager == "pipx":
        return [["pipx", "upgrade", "minder"]]
    if manager == "pip":
        return [[sys.executable, "-m", "pip", "install", "--upgrade", "minder"]]
    return [
        ["uv", "tool", "upgrade", "minder"],
        ["pipx", "upgrade", "minder"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "minder"],
    ]


def _self_update_cli(manager: str) -> None:
    before_version = _installed_package_version()
    target_version = _latest_pypi_version()
    failures: list[str] = []
    for command in _cli_update_commands(manager):
        executable = command[0]
        if executable != sys.executable and shutil.which(executable) is None:
            failures.append(f"{' '.join(command)} -> command not available")
            continue
        print(f"Executing CLI update: {' '.join(command)}")
        result = subprocess.run(
            command,
            capture_output=False,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            after_version = _installed_package_version() or target_version
            print(
                "CLI update completed: "
                f"{before_version or 'unknown'} -> {after_version or 'unknown'} "
                f"via {' '.join(command)}"
            )
            return
        failures.append(f"{' '.join(command)} -> failed with exit code {result.returncode}")
    raise RuntimeError("CLI update failed: " + "; ".join(failures))


def _installer_asset_filename(release_tag: str, *, installer: str) -> str:
    if installer == "powershell":
        return f"install-minder-{release_tag}.ps1"
    return f"install-minder-{release_tag}.sh"


def _prefer_powershell_installer() -> bool:
    return platform.system().lower() == "windows"


def _download_release_installer(
    repository_slug: str,
    release_tag: str,
    *,
    installer: str = "bash",
) -> tuple[str, str]:
    asset_name = _installer_asset_filename(release_tag, installer=installer)
    installer_url = (
        f"https://github.com/{repository_slug}/releases/download/{release_tag}/"
        f"{asset_name}"
    )
    response = httpx.get(installer_url, timeout=10)
    response.raise_for_status()
    return installer_url, response.text


def _run_bash_installer(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash"],
        input=script,
        capture_output=False,
        text=True,
        env=env,
        check=False,
    )


def _run_powershell_installer(
    script: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    executable = "powershell.exe" if platform.system().lower() == "windows" else "pwsh"
    return subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"],
        input=script,
        capture_output=False,
        text=True,
        env=env,
        check=False,
    )


def _self_update_server(install_dir: Path) -> None:
    if not install_dir.is_dir():
        raise ValueError(f"Server install directory does not exist: {install_dir}")
    current, latest, repository_slug, _, has_update = _server_update_available(
        install_dir
    )
    if latest is None:
        raise RuntimeError("Could not determine the latest Minder server release")
    if current is not None and not has_update:
        print(f"Minder server is already up to date ({current})")
        return
    installer_variant = "powershell" if _prefer_powershell_installer() else "bash"
    installer_url, installer_script = _download_release_installer(
        repository_slug, latest, installer=installer_variant
    )
    env_payload = _load_env_file(install_dir / ".env")
    update_env = os.environ.copy()
    update_env["MINDER_INSTALL_DIR"] = str(install_dir)
    for key in ("MINDER_MODELS_DIR", "MINDER_PORT", "MILVUS_PORT", "OPENAI_API_KEY"):
        value = env_payload.get(key)
        if value:
            update_env[key] = value
    print(f"Executing server update for {install_dir}...")
    if installer_variant == "powershell":
        result = _run_powershell_installer(installer_script, update_env)
    else:
        result = _run_bash_installer(installer_script, update_env)
    if result.returncode != 0:
        raise RuntimeError(f"Server update failed with exit code {result.returncode}")
    # Output is already streamed to stdout/stderr in installer helpers if not captured
    print(
        f"Server update completed for {install_dir}: "
        f"{current or 'unknown'} -> {latest}"
    )
    print(f"Release installer: {installer_url}")
    if current:
        print(
            "Rollback guidance: rerun the previous release installer for "
            f"{current} with MINDER_INSTALL_DIR={install_dir}."
        )


def _check_update(args: argparse.Namespace) -> int:
    components = ["cli", "server"] if args.component == "all" else [args.component]
    if "cli" in components:
        _print_cli_update_status()
    if "server" in components:
        install_dir = (
            Path(args.install_dir).expanduser().resolve()
            if args.install_dir
            else _default_server_install_dir()
        )
        _print_server_update_status(install_dir)
    return 0


def _update(args: argparse.Namespace) -> int:
    components = ["cli", "server"] if args.component == "all" else [args.component]
    if "cli" in components:
        _self_update_cli(args.manager)
    if "server" in components:
        install_dir = (
            Path(args.install_dir).expanduser().resolve()
            if args.install_dir
            else _default_server_install_dir()
        )
        _self_update_server(install_dir)
    return 0


def _run_git(
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


def _repo_root(path: str) -> Path:
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=path)
    return Path(result.stdout.strip()).resolve()


def _git_branch(repo_root: Path) -> str | None:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    branch = result.stdout.strip()
    return branch or None


def _git_remote_url(repo_root: Path) -> str | None:
    result = _run_git(
        ["config", "--get", "remote.origin.url"],
        cwd=repo_root,
        check=False,
    )
    remote_url = result.stdout.strip()
    return remote_url or None


def _normalize_repo_remote(remote_url: str | None) -> str | None:
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


def _repo_name_from_remote(remote_url: str | None) -> str | None:
    normalized_remote = _normalize_repo_remote(remote_url)
    if not normalized_remote:
        return None
    _, _, path = normalized_remote.partition(":")
    repo_name = path.rsplit("/", 1)[-1].removesuffix(".git").strip()
    return repo_name or None


def _git_file_delta(
    repo_root: Path, diff_base: str | None = None
) -> tuple[list[str], list[str]]:
    diff_command = ["diff", "--name-only", "--diff-filter=ACMRD"]
    if diff_base:
        diff_command.append(f"{diff_base}...HEAD")
    else:
        diff_command.append("HEAD")
    diff_result = _run_git(diff_command, cwd=repo_root)
    changed = {line.strip() for line in diff_result.stdout.splitlines() if line.strip()}

    deleted_result = _run_git(
        [
            "diff",
            "--name-only",
            "--diff-filter=D",
            *([f"{diff_base}...HEAD"] if diff_base else ["HEAD"]),
        ],
        cwd=repo_root,
    )
    deleted = {
        line.strip() for line in deleted_result.stdout.splitlines() if line.strip()
    }
    changed.difference_update(deleted)

    untracked_result = _run_git(
        ["ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
    )
    changed.update(
        line.strip() for line in untracked_result.stdout.splitlines() if line.strip()
    )
    return sorted(changed), sorted(deleted)


_BRANCH_TOPOLOGY_OVERRIDE_RELATIVE = Path(".minder") / "branch-topology.toml"
_ALLOWED_RELATIONSHIP_DIRECTIONS = ("outbound", "inbound", "bidirectional")


def _gitmodules_submodule_sections(gitmodules_path: Path) -> dict[str, dict[str, str]]:
    """Parse ``.gitmodules`` into a mapping of submodule name to field dict."""
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


def _submodule_branch_relationships(
    repo_root: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    gitmodules = repo_root / ".gitmodules"
    if not gitmodules.is_file():
        return []

    sections = _gitmodules_submodule_sections(gitmodules)
    relationships: list[dict[str, Any]] = []
    for name, fields in sections.items():
        url = (fields.get("url") or "").strip()
        if not url:
            continue
        target_branch = (fields.get("branch") or "").strip() or "main"
        submodule_path = (fields.get("path") or name).strip()
        target_repo_name = (
            _repo_name_from_remote(url) or name.rsplit("/", 1)[-1].strip() or name
        )
        relationships.append(
            {
                "source_branch": source_branch,
                "target_repo_name": target_repo_name,
                "target_repo_url": _normalize_repo_remote(url),
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


def _normalize_relationship_entry(
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
        _normalize_repo_remote(raw_url) if isinstance(raw_url, str) else None
    )

    raw_id = entry.get("target_repo_id")
    target_repo_id = (
        raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None
    )

    direction = str(entry.get("direction") or "outbound").strip() or "outbound"
    if direction not in _ALLOWED_RELATIONSHIP_DIRECTIONS:
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


def _branch_topology_override_relationships(
    repo_root: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    override_path = repo_root / _BRANCH_TOPOLOGY_OVERRIDE_RELATIVE
    if not override_path.is_file():
        return []
    try:
        data = tomllib.loads(override_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []

    raw_entries = data.get("branch_relationships")
    if raw_entries is None:
        raw_entries = data.get("branch_relationship")
    if not isinstance(raw_entries, list):
        return []

    relationships: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entry_copy = dict(entry)
        raw_metadata = entry_copy.get("metadata")
        metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        metadata.setdefault("source", "branch-topology.toml")
        entry_copy["metadata"] = metadata
        normalized = _normalize_relationship_entry(
            entry_copy, fallback_branch=source_branch
        )
        if normalized is not None:
            relationships.append(normalized)
    return relationships


def _dedupe_branch_relationships(
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for entry in relationships:
        key = (
            str(entry.get("source_branch") or ""),
            str(entry.get("target_repo_id") or ""),
            str(entry.get("target_repo_name") or ""),
            str(entry.get("target_branch") or ""),
            str(entry.get("relation") or "depends_on"),
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = dict(entry)
            continue
        merged_metadata = {
            **dict(existing.get("metadata") or {}),
            **dict(entry.get("metadata") or {}),
        }
        merged = {**existing, **entry, "metadata": merged_metadata}
        deduped[key] = merged
    return list(deduped.values())


def _detect_branch_relationships(
    repo_root: Path, source_branch: str | None
) -> list[dict[str, Any]]:
    relationships = _submodule_branch_relationships(repo_root, source_branch)
    relationships.extend(
        _branch_topology_override_relationships(repo_root, source_branch)
    )
    return _dedupe_branch_relationships(relationships)


def _base_http_url(server_url: str) -> str:
    parts = urlsplit(server_url)
    path = parts.path.rstrip("/")
    if path.endswith("/sse"):
        path = path[:-4]
    elif path.endswith("/mcp"):
        path = path[:-4]
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def _sse_url(server_url: str) -> str:
    base_url = _base_http_url(server_url)
    return f"{base_url}/sse"


def _mcp_url(server_url: str) -> str:
    base_url = _base_http_url(server_url)
    return f"{base_url}/mcp"


def _appdata_dir() -> Path:
    appdata = os.getenv("APPDATA", "").strip()
    if appdata:
        return Path(appdata)
    return Path.home() / "AppData" / "Roaming"


def _global_target_path(target: str) -> Path:
    system = platform.system().lower()
    home = Path.home()
    if target == "vscode":
        if system == "darwin":
            return (
                home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
            )
        if system == "windows":
            return _appdata_dir() / "Code" / "User" / "mcp.json"
        return home / ".config" / "Code" / "User" / "mcp.json"
    if target == "cursor":
        if system == "darwin":
            return (
                home
                / "Library"
                / "Application Support"
                / "Cursor"
                / "User"
                / "mcp.json"
            )
        if system == "windows":
            return _appdata_dir() / "Cursor" / "User" / "mcp.json"
        return home / ".config" / "Cursor" / "User" / "mcp.json"
    if target == "claude-code":
        if system == "windows":
            return home / ".claude" / "mcp.json"
        return home / ".claude" / "mcp.json"
    raise ValueError(f"Unsupported MCP target: {target}")


def _local_target_path(target: str, cwd: Path) -> Path:
    if target == "vscode":
        return cwd / ".vscode" / "mcp.json"
    if target == "cursor":
        return cwd / ".cursor" / "mcp.json"
    if target == "claude-code":
        return cwd / ".claude" / "mcp.json"
    raise ValueError(f"Unsupported MCP target: {target}")


def _ide_instruction_path(target: str, cwd: Path) -> Path | None:
    if target == "vscode":
        return cwd / ".github" / "copilot-instructions.md"
    if target == "cursor":
        return cwd / ".cursor" / "rules" / "minder.mdc"
    if target == "claude-code":
        return cwd / "CLAUDE.md"
    return None


def _ide_agent_path(target: str, cwd: Path) -> Path | None:
    if target == "claude-code":
        return cwd / ".claude" / "agents" / "minder-repo-guide.md"
    return None


def _ide_instruction_key(target: str) -> str:
    return f"minder-ide-instructions:{target}"


def _ide_agent_key(target: str) -> str:
    return f"minder-ide-agent:{target}"


def _ide_bootstrap_instruction(target: str) -> str:
    version = _bootstrap_version()
    if target == "vscode":
        return (
            f"Minder repo-local instructions (version {version})\n\n"
            "- Use Minder MCP tools for repository-aware search, impact, workflow, and query flows.\n"
            "- Prefer `minder_workflow_get` or `minder_workflow_step` before making large changes.\n"
            "- Use `minder_query`, `minder_search_graph`, and `minder_find_impact` before broad refactors.\n"
            "- Run `minder sync` after structural repository changes so graph metadata stays current."
        )
    if target == "cursor":
        return (
            "---\n"
            "description: Minder repository guidance\n"
            "globs:\n"
            "alwaysApply: false\n"
            "---\n\n"
            f"Use Minder repo-local automation (version {version}) for repository queries and workflow guidance.\n\n"
            "- Ask Minder for impact and graph context before cross-module edits.\n"
            "- Sync repo metadata with `minder sync` after structural changes.\n"
            "- Keep workflow-aware MCP calls in the loop for non-trivial implementation work."
        )
    if target == "claude-code":
        return (
            f"Minder repo-local instructions (version {version})\n\n"
            "- Use Minder MCP tools as the first source of repository context.\n"
            "- Prefer workflow and graph lookups before broad implementation changes.\n"
            "- Run `minder sync` after structural edits so future queries use fresh repo metadata."
        )
    raise ValueError(f"Unsupported IDE target: {target}")


def _ide_agent_content(target: str) -> str:
    version = _bootstrap_version()
    if target != "claude-code":
        raise ValueError(f"Unsupported IDE target for agent bootstrap: {target}")
    return (
        "---\n"
        "name: minder-repo-guide\n"
        "description: Use Minder MCP tools to gather repository, workflow, and impact context before implementation.\n"
        f"version: {version}\n"
        "---\n\n"
        "Use this agent prompt when you need to explore a repository through Minder before editing code.\n\n"
        "Recommended flow:\n"
        "1. Call Minder workflow and graph tools to understand the current repository state.\n"
        "2. Use Minder query/search tools to narrow the affected code paths.\n"
        "3. Only then move into implementation and resync metadata when structure changes."
    )


def _gitignore_entries_for_targets(targets: list[str]) -> list[str]:
    entries = [".minder/"]
    for target in targets:
        local_path = _local_target_path(target, Path("."))
        entries.append(local_path.as_posix())
    ordered: list[str] = []
    for entry in entries:
        if entry not in ordered:
            ordered.append(entry)
    return ordered


def _metadata_path(cwd: Path) -> Path:
    return cwd / ".minder" / "ide-bootstrap.json"


def _write_bootstrap_metadata(cwd: Path, targets: list[str]) -> None:
    _write_json(
        _metadata_path(cwd),
        {
            "version": _bootstrap_version(),
            "targets": targets,
            "mode": "repo-local",
        },
    )


def _install_repo_local_ide_assets(cwd: Path, targets: list[str]) -> list[Path]:
    installed_paths: list[Path] = []
    for target in targets:
        instruction_path = _ide_instruction_path(target, cwd)
        if instruction_path is not None:
            _upsert_managed_block(
                instruction_path,
                _ide_instruction_key(target),
                _ide_bootstrap_instruction(target),
            )
            installed_paths.append(instruction_path)
        agent_path = _ide_agent_path(target, cwd)
        if agent_path is not None:
            _upsert_managed_block(
                agent_path,
                _ide_agent_key(target),
                _ide_agent_content(target),
            )
            installed_paths.append(agent_path)

    gitignore_path = cwd / ".gitignore"
    _upsert_managed_block(
        gitignore_path,
        _IDE_GITIGNORE_KEY,
        "\n".join(_gitignore_entries_for_targets(targets)),
    )
    installed_paths.append(gitignore_path)
    _write_bootstrap_metadata(cwd, targets)
    installed_paths.append(_metadata_path(cwd))
    return installed_paths


def _remove_repo_local_ide_assets(cwd: Path, targets: list[str]) -> list[Path]:
    removed_paths: list[Path] = []
    for target in targets:
        instruction_path = _ide_instruction_path(target, cwd)
        if instruction_path is not None and _remove_managed_block(
            instruction_path, _ide_instruction_key(target)
        ):
            removed_paths.append(instruction_path)
        agent_path = _ide_agent_path(target, cwd)
        if agent_path is not None and _remove_managed_block(
            agent_path, _ide_agent_key(target)
        ):
            removed_paths.append(agent_path)

    gitignore_path = cwd / ".gitignore"
    if _remove_managed_block(gitignore_path, _IDE_GITIGNORE_KEY):
        removed_paths.append(gitignore_path)
    metadata_path = _metadata_path(cwd)
    if metadata_path.exists():
        metadata_path.unlink()
        removed_paths.append(metadata_path)
    return removed_paths


def _target_root_key(target: str) -> str:
    if target == "vscode":
        return "servers"
    return "mcpServers"


def _target_entry(
    target: str,
    *,
    protocol: str,
    server_url: str,
    client_key: str,
    cwd: Path,
) -> dict[str, Any]:
    normalized_protocol = _normalize_protocol(protocol)
    if normalized_protocol == "stdio":
        entry: dict[str, Any] = {
            "command": "uv",
            "args": ["run", "python", "-m", "minder.server"],
            "cwd": str(cwd),
            "env": {
                "MINDER_SERVER__TRANSPORT": "stdio",
                "MINDER_CLIENT_API_KEY": client_key,
            },
        }
        if target in {"vscode", "cursor"}:
            entry["type"] = "stdio"
        return entry

    sse_url = _sse_url(server_url)
    mcp_url = _mcp_url(server_url)
    if target == "vscode":
        return {
            "type": "sse",
            "url": sse_url,
            "headers": {"X-Minder-Client-Key": client_key},
        }
    if target == "cursor":
        return {
            "url": mcp_url,
            "headers": {"X-Minder-Client-Key": client_key},
        }
    if target == "claude-code":
        return {
            "type": "sse",
            "url": sse_url,
            "headers": {"X-Minder-Client-Key": client_key},
        }
    raise ValueError(f"Unsupported MCP target: {target}")


def _install_target(
    path: Path,
    target: str,
    *,
    protocol: str,
    server_url: str,
    client_key: str,
    cwd: Path,
) -> None:
    payload = _load_json(path)
    root_key = _target_root_key(target)
    payload.setdefault(root_key, {})
    payload[root_key]["minder"] = _target_entry(
        target,
        protocol=protocol,
        server_url=server_url,
        client_key=client_key,
        cwd=cwd,
    )
    if target == "vscode":
        payload.setdefault("inputs", [])
    _write_json(path, payload)


def _uninstall_target(path: Path, target: str) -> bool:
    if not path.is_file():
        return False
    payload = _load_json(path)
    root_key = _target_root_key(target)
    servers = payload.get(root_key)
    if not isinstance(servers, dict) or "minder" not in servers:
        return False
    del servers["minder"]
    if not servers:
        payload.pop(root_key, None)
    if target == "vscode" and payload.get("inputs") == [] and len(payload) == 1:
        payload.pop("inputs", None)
    if not payload:
        path.unlink(missing_ok=True)
        return True
    _write_json(path, payload)
    return True


def _parse_targets(raw_targets: list[str] | None) -> list[str]:
    if not raw_targets:
        return list(_LOCAL_MCP_TARGETS)
    parsed: list[str] = []
    for raw_target in raw_targets:
        value = raw_target.strip().lower()
        if not value:
            continue
        if value == "all":
            parsed.extend(_LOCAL_MCP_TARGETS)
        else:
            parsed.append(value)
    ordered: list[str] = []
    for target in parsed:
        if target not in _LOCAL_MCP_TARGETS:
            raise ValueError(f"Unsupported MCP target: {target}")
        if target not in ordered:
            ordered.append(target)
    return ordered


def _login(args: argparse.Namespace) -> int:
    client_key = (args.client_key or "").strip() or _prompt_client_key()
    if not client_key.startswith("mkc_"):
        raise ValueError("Client key must start with 'mkc_'")

    config_path = Path(args.config_path).expanduser()
    existing = _load_json(config_path)
    default_protocol = _normalize_protocol(
        str(existing.get("protocol", _DEFAULT_PROTOCOL))
    )
    protocol = _normalize_protocol(args.protocol or _prompt_protocol(default_protocol))
    default_server_url = str(existing.get("server_url", _DEFAULT_SERVER_URL)).strip()
    if protocol == "sse":
        server_url = (args.server_url or "").strip() or default_server_url
    else:
        server_url = (args.server_url or "").strip() or default_server_url
    payload = {
        **existing,
        "protocol": protocol,
        "server_url": server_url,
        "client_api_key": client_key,
        "default_headers": {
            "X-Minder-Client-Key": client_key,
        },
    }
    _write_json(config_path, payload)
    print(f"Stored client credentials in {config_path}")
    print(f"Protocol: {protocol}")
    print(f"Server URL: {server_url}")
    print(f"export MINDER_CLIENT_API_KEY={client_key}")
    return 0


def _install_mcp(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path).expanduser()
    settings = _require_client_settings(config_path)
    protocol = str(settings.get("protocol", _DEFAULT_PROTOCOL))
    targets = _parse_targets(args.target)
    install_root = Path(args.cwd).resolve()
    installed_paths: list[Path] = []

    for target in targets:
        path = (
            _global_target_path(target)
            if args.global_install
            else _local_target_path(target, install_root)
        )
        _install_target(
            path,
            target,
            protocol=protocol,
            server_url=str(settings.get("server_url", "")),
            client_key=str(settings["client_api_key"]),
            cwd=install_root,
        )
        installed_paths.append(path)

    for path in installed_paths:
        print(f"Installed Minder MCP config: {path}")
    return 0


def _uninstall_mcp(args: argparse.Namespace) -> int:
    targets = _parse_targets(args.target)
    install_root = Path(args.cwd).resolve()
    removed_count = 0

    for target in targets:
        path = (
            _global_target_path(target)
            if args.global_install
            else _local_target_path(target, install_root)
        )
        if _uninstall_target(path, target):
            removed_count += 1
            print(f"Removed Minder MCP config: {path}")

    if removed_count == 0:
        print("No Minder MCP entries were found to remove")
    return 0


def _install_ide(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path).expanduser()
    settings = _require_client_settings(config_path)
    protocol = str(settings.get("protocol", _DEFAULT_PROTOCOL))
    targets = _parse_targets(args.target)
    install_root = Path(args.cwd).resolve()
    installed_paths: list[Path] = []

    for target in targets:
        path = _local_target_path(target, install_root)
        _install_target(
            path,
            target,
            protocol=protocol,
            server_url=str(settings.get("server_url", "")),
            client_key=str(settings["client_api_key"]),
            cwd=install_root,
        )
        installed_paths.append(path)

    installed_paths.extend(_install_repo_local_ide_assets(install_root, targets))

    for path in installed_paths:
        print(f"Installed Minder IDE asset: {path}")
    return 0


def _uninstall_ide(args: argparse.Namespace) -> int:
    targets = _parse_targets(args.target)
    install_root = Path(args.cwd).resolve()
    removed_paths: list[Path] = []

    for target in targets:
        path = _local_target_path(target, install_root)
        if _uninstall_target(path, target):
            removed_paths.append(path)

    removed_paths.extend(_remove_repo_local_ide_assets(install_root, targets))

    if not removed_paths:
        print("No Minder IDE assets were found to remove")
        return 0
    for path in removed_paths:
        print(f"Removed Minder IDE asset: {path}")
    return 0


def _resolve_repo_id(
    *,
    base_url: str,
    client_key: str,
    repo_root: Path,
    default_branch: str | None,
) -> str:
    remote_url = _normalize_repo_remote(_git_remote_url(repo_root))
    if remote_url is None:
        raise ValueError(
            "Repository remote origin SSH URL is required when --repo-id is omitted"
        )
    response = httpx.post(
        f"{base_url}/v1/client/repositories/resolve",
        headers={"X-Minder-Client-Key": client_key},
        json={
            "repo_name": _repo_name_from_remote(remote_url) or repo_root.name,
            "repo_path": str(repo_root),
            "repo_url": remote_url,
            "default_branch": default_branch,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    repository = payload.get("repository") if isinstance(payload, dict) else None
    repo_id = repository.get("id") if isinstance(repository, dict) else None
    if not isinstance(repo_id, str) or not repo_id.strip():
        raise ValueError("Repository resolve response did not include a repository id")
    return repo_id.strip()


def _sync(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path).expanduser()
    settings = _require_client_settings(config_path)
    protocol = str(settings.get("protocol", _DEFAULT_PROTOCOL))
    if protocol != "sse":
        raise ValueError(
            "minder sync requires protocol 'sse' with a reachable server_url."
        )
    if not args.skip_upgrade_check:
        _maybe_print_upgrade_notice()
    repo_root = _repo_root(args.repo_path)
    branch = _git_branch(repo_root)
    changed_files, deleted_files = _git_file_delta(repo_root, args.diff_base)
    branch_relationships = _detect_branch_relationships(repo_root, branch)
    payload = RepoScanner.build_sync_payload(
        str(repo_root),
        branch=branch,
        diff_base=args.diff_base,
        changed_files=changed_files,
        deleted_files=deleted_files,
        branch_relationships=branch_relationships,
    )

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    base_url = _base_http_url(str(settings["server_url"]))
    headers = {"X-Minder-Client-Key": str(settings["client_api_key"])}
    repo_id = args.repo_id or _resolve_repo_id(
        base_url=base_url,
        client_key=headers["X-Minder-Client-Key"],
        repo_root=repo_root,
        default_branch=branch,
    )
    sync_url = f"{base_url}/v1/client/repositories/{repo_id}/graph-sync"
    response = httpx.post(sync_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
    return 0


def _version(args: argparse.Namespace) -> int:
    version = _installed_package_version()
    if version:
        print(f"minder {version}")
    else:
        print("minder version unknown (not installed as a package)")
    return 0


def _check_version(args: argparse.Namespace) -> int:  # noqa: ARG001
    installed, latest, has_update = _cli_update_available()
    print("CLI version:")
    print(f"  installed: {installed or 'unknown'}")
    print(f"  latest: {latest or 'unknown'}")
    if installed and latest:
        if has_update:
            print(f"  status: update available ({installed} -> {latest})")
        else:
            print("  status: up to date")
    else:
        print("  status: unable to determine latest version")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minder CLI")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"minder {_installed_package_version() or 'unknown'}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Show the Minder CLI version.")
    subparsers.add_parser(
        "check-version",
        help="Show installed CLI version and latest published version.",
    )

    login = subparsers.add_parser(
        "login",
        help="Store Minder client auth + transport settings for CLI commands.",
    )
    login.add_argument(
        "--client-key",
        default=None,
        help="Client API key in mkc_... format. If omitted, prompt securely.",
    )
    login.add_argument(
        "--protocol",
        choices=("sse", "stdio"),
        default=None,
        help="Client protocol mode: sse (remote) or stdio (local process).",
    )
    login.add_argument(
        "--server-url",
        default=None,
        help="Minder server URL. Used for SSE mode and remote sync APIs.",
    )
    login.add_argument(
        "--config-path",
        default=str(_client_config_path()),
        help="Path to the persisted CLI client config file.",
    )

    install_mcp = subparsers.add_parser(
        "install-mcp",
        help="Install Minder MCP config for the current directory or globally.",
    )
    install_mcp.add_argument(
        "--config-path",
        default=str(_client_config_path()),
        help="Path to the persisted CLI client config file.",
    )
    install_mcp.add_argument(
        "--target",
        action="append",
        help="MCP target to install: vscode, cursor, claude-code, or all. Repeatable.",
    )
    install_mcp.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install into user-level config paths instead of the current workspace.",
    )
    install_mcp.add_argument(
        "--cwd",
        default=".",
        help="Workspace directory to install local MCP config into.",
    )

    uninstall_mcp = subparsers.add_parser(
        "uninstall-mcp",
        help="Remove Minder MCP config from the current directory or global config.",
    )
    uninstall_mcp.add_argument(
        "--target",
        action="append",
        help="MCP target to uninstall: vscode, cursor, claude-code, or all. Repeatable.",
    )
    uninstall_mcp.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Remove from user-level config paths instead of the current workspace.",
    )
    uninstall_mcp.add_argument(
        "--cwd",
        default=".",
        help="Workspace directory to remove local MCP config from.",
    )

    install_ide = subparsers.add_parser(
        "install-ide",
        help="Install repo-local Minder MCP config plus IDE instruction and agent assets.",
    )
    install_ide.add_argument(
        "--config-path",
        default=str(_client_config_path()),
        help="Path to the persisted CLI client config file.",
    )
    install_ide.add_argument(
        "--target",
        action="append",
        help="IDE target to install: vscode, cursor, claude-code, or all. Repeatable.",
    )
    install_ide.add_argument(
        "--cwd",
        default=".",
        help="Workspace directory to install repo-local IDE assets into.",
    )

    uninstall_ide = subparsers.add_parser(
        "uninstall-ide",
        help="Remove repo-local Minder IDE bootstrap assets from the current workspace.",
    )
    uninstall_ide.add_argument(
        "--target",
        action="append",
        help="IDE target to uninstall: vscode, cursor, claude-code, or all. Repeatable.",
    )
    uninstall_ide.add_argument(
        "--cwd",
        default=".",
        help="Workspace directory to remove repo-local IDE assets from.",
    )

    check_update = subparsers.add_parser(
        "check-update",
        help="Check for newer published Minder CLI and server releases.",
    )
    check_update.add_argument(
        "--component",
        choices=("cli", "server", "all"),
        default="all",
        help="Which installed component to inspect for available updates.",
    )
    check_update.add_argument(
        "--install-dir",
        default=None,
        help="Server install directory to inspect. Defaults to ~/.minder/current or the newest release directory.",
    )

    update = subparsers.add_parser(
        "update",
        help="Apply an update for the Minder CLI, server deployment, or both.",
    )
    update.add_argument(
        "--component",
        choices=("cli", "server", "all"),
        default="cli",
        help="Which component to update.",
    )
    update.add_argument(
        "--manager",
        choices=("auto", "uv", "pipx", "pip"),
        default="auto",
        help="Preferred package manager for CLI update.",
    )
    update.add_argument(
        "--install-dir",
        default=None,
        help="Server install directory to update. Defaults to ~/.minder/current or the newest release directory.",
    )

    self_update = subparsers.add_parser(
        "self-update",
        help=argparse.SUPPRESS,
    )
    self_update.add_argument(
        "--component",
        choices=("cli", "server", "all"),
        default="cli",
        help=argparse.SUPPRESS,
    )
    self_update.add_argument(
        "--manager",
        choices=("auto", "uv", "pipx", "pip"),
        default="auto",
        help=argparse.SUPPRESS,
    )
    self_update.add_argument(
        "--install-dir",
        default=None,
        help=argparse.SUPPRESS,
    )

    sync = subparsers.add_parser(
        "sync",
        help="Build a delta payload from git diff and sync graph metadata using the stored client key.",
    )
    sync.add_argument(
        "--repo-id",
        required=False,
        help="Repository UUID registered on the Minder server. If omitted, the CLI resolves it from the current repo.",
    )
    sync.add_argument(
        "--repo-path",
        default=".",
        help="Path inside the git repository to sync. Defaults to the current directory.",
    )
    sync.add_argument(
        "--diff-base",
        default=None,
        help="Optional git base ref for delta calculation, e.g. origin/main.",
    )
    sync.add_argument(
        "--config-path",
        default=str(_client_config_path()),
        help="Path to the persisted CLI client config file.",
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the built payload instead of sending it to the server.",
    )
    sync.add_argument(
        "--skip-upgrade-check",
        action="store_true",
        help="Skip checking PyPI for a newer CLI version before syncing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "login":
        return _login(args)
    if args.command == "install-mcp":
        return _install_mcp(args)
    if args.command == "uninstall-mcp":
        return _uninstall_mcp(args)
    if args.command == "install-ide":
        return _install_ide(args)
    if args.command == "uninstall-ide":
        return _uninstall_ide(args)
    if args.command == "check-update":
        return _check_update(args)
    if args.command in {"update", "self-update"}:
        return _update(args)
    if args.command == "sync":
        return _sync(args)
    if args.command == "version":
        return _version(args)
    if args.command == "check-version":
        return _check_version(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
