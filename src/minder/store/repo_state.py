from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RepoStateStore:
    def __init__(self, state_dir_name: str = ".minder") -> None:
        self._state_dir_name = state_dir_name

    async def read_all(self, repo_path: str, branch: str = "main") -> dict[str, Any]:
        state_dir = self._ensure_state_dir(repo_path, branch)
        return {
            "workflow": self._read_json(state_dir / "workflow.json", default={}),
            "context": self._read_json(state_dir / "context.json", default={}),
            "relationships": self._read_json(state_dir / "relationships.json", default={}),
            "artifacts": self._read_artifacts(state_dir / "artifacts"),
        }

    async def write_workflow_state(self, repo_path: str, payload: dict[str, Any], branch: str = "main") -> None:
        self._write_json(self._ensure_state_dir(repo_path, branch) / "workflow.json", payload)

    async def write_context(self, repo_path: str, payload: dict[str, Any], branch: str = "main") -> None:
        self._write_json(self._ensure_state_dir(repo_path, branch) / "context.json", payload)

    async def write_relationships(self, repo_path: str, payload: dict[str, Any], branch: str = "main") -> None:
        self._write_json(self._ensure_state_dir(repo_path, branch) / "relationships.json", payload)

    async def write_artifact(self, repo_path: str, name: str, content: str, branch: str = "main") -> None:
        artifacts_dir = self._ensure_state_dir(repo_path, branch) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / name).write_text(content, encoding="utf-8")

    def _ensure_state_dir(self, repo_path: str, branch: str = "main") -> Path:
        base_dir = Path(repo_path) / self._state_dir_name
        
        # Phase 3: Auto-generate .gitignore in the base directory to prevent merge conflicts
        if not base_dir.exists():
            base_dir.mkdir(parents=True, exist_ok=True)
            gitignore = base_dir / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text("*\n", encoding="utf-8")
                
        # Branch isolation: normalize branch name to be safe for file system
        safe_branch = "".join(c if c.isalnum() or c in "-_" else "_" for c in branch)
        state_dir = base_dir / safe_branch
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    @staticmethod
    def _read_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _read_artifacts(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        return {
            item.name: item.read_text(encoding="utf-8")
            for item in sorted(path.iterdir())
            if item.is_file()
        }
