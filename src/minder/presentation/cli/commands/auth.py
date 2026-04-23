from __future__ import annotations

import argparse
from pathlib import Path

from ..utils.common import client_config_path, write_json, load_json
from ..utils.config import prompt_client_key, prompt_protocol, normalize_protocol


def login_command(args: argparse.Namespace) -> int:
    """Store Minder client auth + transport settings for CLI commands."""
    config_path = Path(args.config_path or client_config_path()).expanduser().resolve()
    
    # Load existing to preserve other settings
    payload = load_json(config_path)
    
    print(f"Configuring Minder CLI at {config_path}")
    
    # Client Key
    client_key = args.client_key
    if not client_key:
        client_key = prompt_client_key()
    payload["client_api_key"] = client_key
    
    # Protocol
    protocol = args.protocol
    if not protocol:
        protocol = prompt_protocol()
    payload["protocol"] = normalize_protocol(protocol)
    
    # Server URL
    server_url = args.server_url
    if not server_url and payload["protocol"] == "sse":
        existing_url = payload.get("server_url")
        prompt = "Minder server URL"
        if existing_url:
            prompt += f" (default: {existing_url})"
        url_input = input(f"{prompt}: ").strip()
        server_url = url_input or existing_url
        if not server_url:
            print("Error: Server URL is required for SSE protocol.")
            return 1
            
    if server_url:
        payload["server_url"] = server_url
        
    # Maintain default_headers for backward compatibility
    payload["default_headers"] = {"X-Minder-Client-Key": client_key}
    
    write_json(config_path, payload)
    print(f"\nSuccess! Stored client credentials in {config_path}")
    print(f"Protocol: {payload['protocol']}")
    print("\nYou can also set these via environment variables:")
    print(f"  export MINDER_CLIENT_API_KEY={client_key}")
    if payload['protocol'] == "sse":
        print(f"  export MINDER_SERVER_URL={payload.get('server_url')}")
        
    return 0
