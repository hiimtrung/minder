from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from minder.graph.state import GraphState


class VerificationRunner(Protocol):
    def run_python(self, code: str, timeout_seconds: int, repo_path: str | None) -> dict[str, object]:
        ...


class SubprocessVerificationRunner:
    def run_python(
        self,
        code: str,
        timeout_seconds: int,
        repo_path: str | None,
    ) -> dict[str, object]:
        cwd = repo_path or "."
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "snippet.py"
            script_path.write_text(code, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout_seconds,
                check=False,
            )
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "runner": "subprocess",
            "timeout_seconds": timeout_seconds,
        }


class DockerSandboxRunner:
    def run_python(
        self,
        code: str,
        timeout_seconds: int,
        repo_path: str | None,
    ) -> dict[str, object]:
        docker_binary = shutil.which("docker")
        if docker_binary is None:
            return {
                "passed": False,
                "returncode": 127,
                "stdout": "",
                "stderr": "docker binary not available",
                "runner": "docker",
                "timeout_seconds": timeout_seconds,
            }

        cwd = repo_path or "."
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "snippet.py"
            script_path.write_text(code, encoding="utf-8")
            completed = subprocess.run(
                [
                    docker_binary,
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "-v",
                    f"{temp_dir}:/workspace:ro",
                    "-w",
                    "/workspace",
                    "minder-sandbox:latest",
                    "python",
                    "snippet.py",
                ],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout_seconds,
                check=False,
            )
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "runner": "docker",
            "timeout_seconds": timeout_seconds,
            "repo_path": repo_path,
        }


class VerificationNode:
    def __init__(
        self,
        sandbox: str = "docker",
        timeout_seconds: int = 30,
        docker_runner: VerificationRunner | None = None,
        subprocess_runner: VerificationRunner | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds
        self._docker_runner = docker_runner or DockerSandboxRunner()
        self._subprocess_runner = subprocess_runner or SubprocessVerificationRunner()

    def run(self, state: GraphState) -> GraphState:
        payload = state.metadata.get("verification_payload")
        if payload is None:
            state.verification_result = {
                "passed": True,
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "runner": self._sandbox,
                "skipped": True,
                "timeout_seconds": self._timeout_seconds,
            }
            return state

        if payload.get("language") != "python":
            state.verification_result = {
                "passed": False,
                "returncode": 1,
                "stdout": "",
                "runner": self._sandbox,
                "stderr": "Unsupported verification language",
                "timeout_seconds": self._timeout_seconds,
            }
            return state

        code = str(payload.get("code", ""))
        if self._sandbox == "subprocess":
            result = self._subprocess_runner.run_python(
                code, self._timeout_seconds, state.repo_path
            )
        else:
            result = self._docker_runner.run_python(
                code, self._timeout_seconds, state.repo_path
            )
        state.verification_result = result
        return state
