"""A tiny mock ACP agent for testing AcpRunner/AcpClient.

Speaks newline-delimited JSON-RPC 2.0 over stdio: answers initialize, session/new,
and session/prompt (emitting one session/update then ending the turn). It also
issues a session/request_permission so the client's auto-approve path is exercised.
"""

import json
import sys


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        mid = msg.get("id")

        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
        elif method == "session/new":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-mock-1"}})
        elif method == "session/prompt":
            # stream one update
            _send({"jsonrpc": "2.0", "method": "session/update", "params": {
                "sessionId": "sess-mock-1",
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "working"}},
            }})
            # ask permission (client should auto-approve)
            _send({"jsonrpc": "2.0", "id": 9001, "method": "session/request_permission", "params": {
                "sessionId": "sess-mock-1",
                "options": [
                    {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                    {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                ],
            }})
            # respond to the prompt — end the turn
            _send({"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}})
        else:
            if mid is not None:
                _send({"jsonrpc": "2.0", "id": mid, "result": {}})


if __name__ == "__main__":
    main()
