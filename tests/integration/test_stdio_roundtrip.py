import asyncio
import json
import pytest
import shutil
import subprocess
import sys
import os
from pathlib import Path

# Skip if uv is not available
@pytest.fixture(scope="module")
def uv_path():
    path = shutil.which("uv")
    if not path:
        pytest.skip("uv not found")
    return path


def _readline_with_timeout(pipe, timeout_s: float) -> str:
    """Read a single line from `pipe` with a hard wall-clock timeout.

    The old implementation relied on `pipe.readline()` which blocks forever if
    the child never writes a newline — a frequent cause of CI hangs. We spawn
    a **daemon** reader thread so, on timeout, we can fail fast without the
    ThreadPoolExecutor-style `shutdown(wait=True)` deadlock. The orphan thread
    dies with the process at interpreter exit.
    """
    import threading

    result: dict[str, object] = {}
    done = threading.Event()

    def _read() -> None:
        try:
            result["value"] = pipe.readline()
        except Exception as exc:  # pragma: no cover - defensive
            result["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_read, daemon=True).start()
    if not done.wait(timeout_s):
        pytest.fail(f"Subprocess stdout.readline() timed out after {timeout_s}s")
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return str(result.get("value", ""))


@pytest.mark.slow
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_stdio_roundtrip(tmp_path, uv_path):
    # Prepare a test workspace
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "hello.py").write_text("print('hello')", encoding="utf-8")

    # Start the minder server in stdio mode as a subprocess.
    # We use `sys.executable` (the same interpreter that's running pytest)
    # instead of `uv run`. `uv run` re-resolves the lockfile on every call
    # which can add tens of seconds on a cold CI cache and occasionally
    # blocks on network I/O — both pure hang hazards for a stdio test.
    env = os.environ.copy()
    env["MINDER_SERVER__TRANSPORT"] = "stdio"
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

    # We'll use a mocked in-memory DB for this test to avoid needing a real MongoDB
    env["MINDER_RELATIONAL_STORE__PROVIDER"] = "sqlite"
    env["MINDER_RELATIONAL_STORE__DB_PATH"] = ":memory:"
    # Keep vector store local-only so repo .env overrides (e.g. milvus) do not block startup.
    env["MINDER_VECTOR_STORE__PROVIDER"] = "milvus_lite"

    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "minder.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent.parent),
        env=env,
        text=True,
        bufsize=1,
    )

    try:
        # Give it a second to start
        await asyncio.sleep(2)

        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f"Server failed to start. Stdout: {stdout}\nStderr: {stderr}")

        # Send 'initialize' request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.1.0"},
            },
        }

        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read the 'initialize' response with a wall-clock bound.
        response_line = _readline_with_timeout(process.stdout, timeout_s=30.0)
        assert response_line, "No response from server"
        response = json.loads(response_line)
        assert response.get("id") == 1
        assert "capabilities" in response.get("result", {})

        # Send 'initialized' notification
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        process.stdin.flush()

        # Call 'list_tools'
        list_tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        process.stdin.write(json.dumps(list_tools_request) + "\n")
        process.stdin.flush()

        # Read responses until we see id=2. Cap the number of iterations so
        # an unexpected notification stream cannot spin forever.
        for _ in range(50):
            line = _readline_with_timeout(process.stdout, timeout_s=15.0)
            if not line:
                pytest.fail("Server closed stdout before returning tools/list")
            resp = json.loads(line)
            if resp.get("id") == 2:
                tools = resp["result"]["tools"]
                tool_names = [t["name"] for t in tools]
                assert "minder_query" in tool_names
                break
        else:
            pytest.fail("Did not receive tools/list response within 50 messages")

    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
