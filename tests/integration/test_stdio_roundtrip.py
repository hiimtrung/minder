import asyncio
import json
import pytest
import shutil
import subprocess
import os
from pathlib import Path

# Skip if uv is not available
@pytest.fixture(scope="module")
def uv_path():
    path = shutil.which("uv")
    if not path:
        pytest.skip("uv not found")
    return path

@pytest.mark.asyncio
async def test_stdio_roundtrip(tmp_path, uv_path):
    # Prepare a test workspace
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    
    # Start the minder server in stdio mode as a subprocess
    # We use 'uv run' to ensure all dependencies are there
    env = os.environ.copy()
    env["MINDER_SERVER__TRANSPORT"] = "stdio"
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
    
    # We'll use a mocked in-memory DB for this test to avoid needing a real MongoDB
    env["MINDER_RELATIONAL_STORE__PROVIDER"] = "sqlite"
    env["MINDER_RELATIONAL_STORE__DB_PATH"] = ":memory:"
    
    process = subprocess.Popen(
        [uv_path, "run", "python", "-m", "minder.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent.parent),
        env=env,
        text=True,
        bufsize=1
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
                "clientInfo": {"name": "test-client", "version": "0.1.0"}
            }
        }
        
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Read the 'initialize' response
        # It should send 'initialized' notification, and potentially other things
        # FastMCP usually sends the response quite quickly
        
        response_line = process.stdout.readline()
        assert response_line, "No response from server"
        response = json.loads(response_line)
        assert response.get("id") == 1
        assert "capabilities" in response.get("result", {})

        # Send 'initialized' notification
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()

        # Call 'list_tools'
        list_tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        process.stdin.write(json.dumps(list_tools_request) + "\n")
        process.stdin.flush()
        
        # Read response
        # Note: There might be some intermediate notifications
        while True:
            line = process.stdout.readline()
            if not line:
                break
            resp = json.loads(line)
            if resp.get("id") == 2:
                tools = resp["result"]["tools"]
                tool_names = [t["name"] for t in tools]
                assert "minder_query" in tool_names
                break
                
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
