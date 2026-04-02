from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
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
        try:
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
        except subprocess.TimeoutExpired as exc:
            return {
                "passed": False,
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "subprocess verification timed out",
                "runner": "subprocess",
                "timeout_seconds": timeout_seconds,
                "failure_kind": "timeout",
                "retryable": False,
            }
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "runner": "subprocess",
            "timeout_seconds": timeout_seconds,
            "failure_kind": "runtime_error" if completed.returncode != 0 else None,
            "retryable": False,
        }


class DockerSandboxRunner:
    def __init__(self, image: str = "minder-sandbox:latest") -> None:
        self._image = image

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
                "failure_kind": "docker_unavailable",
                "retryable": False,
            }

        cwd = repo_path or "."
        inspect = subprocess.run(
            [docker_binary, "image", "inspect", self._image],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )
        if inspect.returncode != 0:
            failure_kind = "image_missing"
            stderr = inspect.stderr or f"docker image '{self._image}' not available"
            lowered = stderr.lower()
            if "permission denied" in lowered or "cannot connect" in lowered or "daemon" in lowered:
                failure_kind = "docker_daemon_unavailable"
            return {
                "passed": False,
                "returncode": inspect.returncode,
                "stdout": inspect.stdout,
                "stderr": stderr,
                "runner": "docker",
                "timeout_seconds": timeout_seconds,
                "failure_kind": failure_kind,
                "retryable": False,
            }

        try:
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
                        "--read-only",
                        "-v",
                        f"{temp_dir}:/workspace:ro",
                        "-w",
                        "/workspace",
                        self._image,
                        "python",
                        "snippet.py",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=timeout_seconds,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            return {
                "passed": False,
                "returncode": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "docker verification timed out",
                "runner": "docker",
                "timeout_seconds": timeout_seconds,
                "failure_kind": "timeout",
                "retryable": False,
            }

        failure_kind = None
        retryable = False
        if completed.returncode != 0:
            failure_kind = "container_error"
            retryable = False
        return {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "runner": "docker",
            "timeout_seconds": timeout_seconds,
            "repo_path": repo_path,
            "failure_kind": failure_kind,
            "retryable": retryable,
        }


class VerificationNode:
    def __init__(
        self,
        sandbox: str = "docker",
        timeout_seconds: int = 30,
        docker_runner: VerificationRunner | None = None,
        subprocess_runner: VerificationRunner | None = None,
        image: str = "minder-sandbox:latest",
    ) -> None:
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds
        self._docker_runner = docker_runner or DockerSandboxRunner(image=image)
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
                "failure_kind": None,
                "retryable": False,
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
                "failure_kind": "unsupported_language",
                "retryable": False,
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
        state.verification_result = self._normalize_result(result)
        return state

    @staticmethod
    def _normalize_result(result: dict[str, object]) -> dict[str, object]:
        normalized: dict[str, Any] = dict(result)
        normalized.setdefault("failure_kind", None if normalized.get("passed") else "runtime_error")
        normalized.setdefault("retryable", False)
        normalized.setdefault("stdout", "")
        normalized.setdefault("stderr", "")
        normalized.setdefault("returncode", 0 if normalized.get("passed") else 1)
        return normalized
