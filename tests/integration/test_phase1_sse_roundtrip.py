import asyncio
import json
import pytest
import shutil
import subprocess
import os
import httpx
import time
from pathlib import Path

@pytest.fixture(scope="module")
def uv_path():
    path = shutil.which("uv")
    if not path:
        pytest.skip("uv not found")
    return path

@pytest.mark.asyncio
async def test_sse_roundtrip(tmp_path, uv_path):
    # Port for test server
    port = 8081
    
    # Start the minder server in sse mode as a subprocess
    env = os.environ.copy()
    env["MINDER_SERVER__TRANSPORT"] = "sse"
    env["MINDER_SERVER__HOST"] = "127.0.0.1"
    env["MINDER_SERVER__PORT"] = str(port)
    env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
    
    # Use a real file for SQLite so we can seed it before starting the server
    db_file = tmp_path / "test.db"
    env["MINDER_RELATIONAL_STORE__DB_PATH"] = str(db_file)
    env["MINDER_RELATIONAL_STORE__PROVIDER"] = "sqlite"
    env["MINDER_VECTOR_STORE__PROVIDER"] = "memory"
    env["MINDER_EMBEDDING__PROVIDER"] = "openai"
    env["MINDER_EMBEDDING__OPENAI_API_KEY"] = "sk-fake"
    env["MINDER_LLM__PROVIDER"] = "openai"
    env["MINDER_LLM__OPENAI_API_KEY"] = "sk-fake"

    # Seed the admin user
    seed_env = env.copy()
    seed_env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")
    seed_res = subprocess.run(
        [uv_path, "run", "python", "scripts/create_admin.py", 
         "--email", "admin@example.com", 
         "--username", "admin", 
         "--display-name", "Admin"],
        env=seed_env,
        check=True,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent.parent)
    )
    # Extract API key from output
    api_key = None
    for line in seed_res.stdout.splitlines():
        if line.startswith("API key: "):
            api_key = line.split(":", 1)[1].strip()
            break
    if not api_key:
         pytest.fail(f"Could not find API key in seed output: {seed_res.stdout}")
    
    print(f"DEBUG: Seeded admin with key: {api_key}")

    stderr_log = tmp_path / "server_stderr.log"
    stderr_file = open(stderr_log, "w")
    
    process = subprocess.Popen(
        [uv_path, "run", "python", "-m", "minder.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        cwd=str(Path(__file__).parent.parent.parent),
        env=env,
        text=True
    )

    try:
        # Wait for the server to start by checking the port
        import socket
        import time
        
        start_time = time.time()
        connected = False
        print(f"DEBUG: Waiting for server on 127.0.0.1:{port}...")
        while time.time() - start_time < 90: # Increase to 90s for safety
            if process.poll() is not None:
                # Read from the log file instead of process.stderr
                stderr_file.flush()
                stderr_content = stderr_log.read_text()
                pytest.fail(f"Server crashed during startup. Stderr:\n{stderr_content}")
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    connected = True
                    break
            await asyncio.sleep(2)
        
        if not connected:
            lsof_res = subprocess.run(["lsof", "-i", f":{port}"], capture_output=True, text=True)
            pytest.fail(f"Server timed out starting on 127.0.0.1:{port}. Lsof:\n{lsof_res.stdout}")

        print(f"DEBUG: Server is listening on 127.0.0.1:{port}. Connecting via HTTP...")
        async with httpx.AsyncClient() as client:
            try:
                # 1. Connect to SSE
                async with client.stream("GET", f"http://127.0.0.1:{port}/sse", timeout=60.0) as response:
                    assert response.status_code == 200
                    
                    endpoint_url = None
                    responses = {}
                    print(f"DEBUG: STARTING TO READ SSE STREAM FROM http://127.0.0.1:{port}/sse")
                    
                    async for line in response.aiter_lines():
                        print(f"DEBUG: SSE LINE: {line}")
                        if line.startswith("data: "):
                            data_str = line[len("data: "):].strip()
                            
                            # If we don't have endpoint yet, the first data is the endpoint
                            if endpoint_url is None:
                                endpoint_path = data_str
                                endpoint_url = f"http://127.0.0.1:{port}{endpoint_path}" if not endpoint_path.startswith("http") else endpoint_path
                                print(f"DEBUG: Got endpoint URL: {endpoint_url}")
                                
                                # Send INITIALIZE request (MANDATORY for MCP)
                                init_request = {
                                    "jsonrpc": "2.0",
                                    "id": 0,
                                    "method": "initialize",
                                    "params": {
                                        "protocolVersion": "2024-11-05",
                                        "capabilities": {},
                                        "clientInfo": {"name": "test-client", "version": "1.0.0"}
                                    }
                                }
                                await client.post(endpoint_url, json=init_request)
                                continue

                            if not data_str.startswith("{"):
                                continue
                            msg = json.loads(data_str)
                            
                            # Handle initialize response
                            if msg.get("id") == 0:
                                print("DEBUG: Received initialize response. Sending initialized notification...")
                                initialized_notif = {
                                    "jsonrpc": "2.0",
                                    "method": "notifications/initialized"
                                }
                                await client.post(endpoint_url, json=initialized_notif)
                                
                                # Now we can call tools!
                                # 2. Call a tool WITHOUT auth
                                await client.post(endpoint_url, json={
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "tools/call",
                                    "params": {
                                        "name": "minder_auth_login",
                                        "arguments": {"api_key": api_key}
                                    }
                                })
                                
                                # 3. Call a tool that REQUIRES auth WITHOUT HEADER (should fail)
                                await client.post(endpoint_url, json={
                                    "jsonrpc": "2.0",
                                    "id": 2,
                                    "method": "tools/call",
                                    "params": {
                                        "name": "minder_auth_ping",
                                        "arguments": {"message": "hello"}
                                    }
                                })
            
                                # 4. Get a token via login first then call ping WITH HEADER
                                await client.post(endpoint_url, json={
                                    "jsonrpc": "2.0",
                                    "id": 3,
                                    "method": "tools/call",
                                    "params": {
                                        "name": "minder_auth_login",
                                        "arguments": {"api_key": api_key}
                                    }
                                })
                                continue

                            # If we have endpoint and it's not initialize, parse as JSON-RPC response
                            if "id" in msg:
                                responses[msg["id"]] = msg
                                if msg["id"] == 1:
                                    pass # login ok, but we don't have user yet in memory
                                if msg["id"] == 2:
                                    # Expected failure
                                    pass
                                if msg["id"] == 3:
                                    # Now we have a token! Try id 4 with auth header
                                    print(f"DEBUG: Tool result for id 3: {msg['result']}")
                                    content = msg["result"].get("content", [])
                                    if not content:
                                         pytest.fail(f"No content in login response: {msg}")
                                    
                                    text = content[0].get("text", "")
                                    print(f"DEBUG: text for id 3: {text!r}")
                                    token_data = json.loads(text)
                                    token = token_data["token"]
                                    
                                    await client.post(endpoint_url, 
                                        json={
                                            "jsonrpc": "2.0",
                                            "id": 4,
                                            "method": "tools/call",
                                            "params": {
                                                "name": "minder_auth_ping",
                                                "arguments": {"message": "authed hello"}
                                            }
                                        },
                                        headers={"Authorization": f"Bearer {token}"}
                                    )
                                    continue

                                if msg["id"] == 4:
                                    # Should succeed!
                                    if len(responses) >= 4:
                                        break
                    
                    assert endpoint_url, "Did not receive endpoint URL"
                    print(f"DEBUG: FINAL RESPONSES: {responses}")
                    assert 1 in responses
                    assert 2 in responses
                    assert 3 in responses
                    assert 4 in responses
                    
                    # Check auth failure message in MCP result for id 2
                    data2 = responses[2]
                    assert data2.get("result", {}).get("isError") is True
                    content_text2 = str(data2.get("result", {}).get("content", []))
                    assert "Authorization header is required" in content_text2

                    # Check auth success for id 4
                    data4 = responses[4]
                    assert data4.get("result", {}).get("isError") is None # Success
                    content_text4 = data4["result"]["content"][0]["text"]
                    assert "auth pong: authed hello" in content_text4
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                pytest.fail(f"Connection failed: {e}")
                
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
        stderr_file.close()
        if stderr_log.exists():
            print(f"DEBUG: SERVER STDERR:\n{stderr_log.read_text()}")
