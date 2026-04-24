from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from ..utils.git import (
    repo_root,
    git_branch,
    git_remote_url,
    git_file_delta,
    detect_branch_relationships,
    normalize_repo_remote,
    repo_name_from_remote,
    run_git,
)
from ..utils.config import require_client_settings
from ..utils.version import maybe_print_upgrade_notice
from ..utils.common import base_http_url
from minder.tools.repo_scanner import RepoScanner


def _resolve_repo_id(
    *,
    base_url: str,
    client_key: str,
    repo_root_path: Path,
    default_branch: str | None,
) -> tuple[str, dict[str, Any] | None]:
    remote_url = normalize_repo_remote(git_remote_url(repo_root_path))
    if remote_url is None:
        raise ValueError(
            "Repository remote origin SSH URL is required when --repo-id is omitted"
        )
    response = httpx.post(
        f"{base_url}/v1/client/repositories/resolve",
        headers={"X-Minder-Client-Key": client_key},
        json={
            "repo_name": repo_name_from_remote(remote_url) or repo_root_path.name,
            "repo_path": str(repo_root_path),
            "repo_url": remote_url,
            "default_branch": default_branch,
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    repository = payload.get("repository") if isinstance(payload, dict) else None
    repo_id = repository.get("id") if isinstance(repository, dict) else None
    last_sync = payload.get("last_sync") if isinstance(payload, dict) else None
    return str(repo_id or "").strip(), last_sync


def _fetch_repo_last_sync(
    *,
    base_url: str,
    client_key: str,
    repo_id: str,
) -> dict[str, Any] | None:
    response = httpx.get(
        f"{base_url}/v1/client/repositories/{repo_id}",
        headers={"X-Minder-Client-Key": client_key},
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    return payload.get("last_sync") if isinstance(payload, dict) else None


def sync_command(args: argparse.Namespace) -> int:
    """Build a delta payload from git diff and sync graph metadata."""
    if not args.skip_upgrade_check:
        maybe_print_upgrade_notice()
        
    config_path = Path(args.config_path).expanduser().resolve()
    settings = require_client_settings(config_path)
    
    root = repo_root(args.repo_path)
    branch = git_branch(root)
    
    server_url = settings.get("server_url")
    if not server_url:
        print("Error: server_url is required for sync. Run 'minder login' to configure.")
        return 1
    
    base_url = base_http_url(str(server_url))
    headers = {"X-Minder-Client-Key": str(settings["client_api_key"])}
    
    try:
        if args.repo_id:
            repo_id = args.repo_id
            try:
                last_sync = _fetch_repo_last_sync(
                    base_url=base_url,
                    client_key=headers["X-Minder-Client-Key"],
                    repo_id=repo_id,
                )
            except (httpx.HTTPError, RuntimeError):
                # Fallback to full sync if we can't fetch last_sync
                last_sync = None
        else:
            repo_id, last_sync = _resolve_repo_id(
                base_url=base_url,
                client_key=headers["X-Minder-Client-Key"],
                repo_root_path=root,
                default_branch=branch,
            )
    except (httpx.HTTPError, RuntimeError, ValueError) as e:
        print(f"Failed to resolve repository: {e}")
        return 1

    diff_base = args.diff_base
    if not diff_base and last_sync:
        diff_base = last_sync.get("commit_hash")
        if diff_base:
            print(f"  Using last sync commit as diff base: {diff_base[:8]}", file=sys.stderr)

    commit_hash = None
    try:
        commit_hash = run_git(["rev-parse", "HEAD"], cwd=root).stdout.strip()
    except Exception:
        pass

    if not args.diff_base and last_sync and commit_hash:
        last_synced_commit = last_sync.get("commit_hash", "")
        last_synced_branch = last_sync.get("branch")
        if (
            last_synced_commit
            and commit_hash == last_synced_commit
            and (last_synced_branch is None or last_synced_branch == branch)
        ):
            print(
                f"Already up to date on '{branch}' (HEAD={commit_hash[:8]}), nothing to sync.",
                file=sys.stderr,
            )
            return 0

    changed, deleted = git_file_delta(root, diff_base)
    relationships = detect_branch_relationships(root, branch)
    
    def progress(msg: str) -> None:
        sys.stderr.write(f"  {msg}\n")
        sys.stderr.flush()

    print(f"Syncing {root.name} ({branch})...", file=sys.stderr)
    payload = RepoScanner.build_sync_payload(
        str(root),
        branch=branch,
        diff_base=diff_base,
        changed_files=changed,
        deleted_files=deleted,
        branch_relationships=relationships,
        commit_hash=commit_hash,
        progress_callback=progress,
    )
    
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
        
    try:
        sync_url = f"{base_url}/v1/client/repositories/{repo_id}/graph-sync"
        print(f"Sending payload to {base_url} (timeout=300s)...", file=sys.stderr)
        response = httpx.post(sync_url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    except (httpx.HTTPError, RuntimeError) as e:
        print(f"Sync failed: {e}")
        return 1
    
    return 0
