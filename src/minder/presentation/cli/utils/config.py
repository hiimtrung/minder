from __future__ import annotations

from getpass import getpass
from pathlib import Path
from typing import Any

from .common import load_json, _DEFAULT_PROTOCOL


def prompt_client_key() -> str:
    client_key = getpass("Minder client key (mkc_...): ").strip()
    if not client_key:
        raise ValueError("Client key is required")
    return client_key


def prompt_protocol(default: str = _DEFAULT_PROTOCOL) -> str:
    value = input(f"Minder protocol [sse/stdio] (default: {default}): ").strip().lower()
    return value or default


def normalize_protocol(raw_protocol: str | None) -> str:
    protocol = (raw_protocol or "").strip().lower() or _DEFAULT_PROTOCOL
    if protocol not in {"sse", "stdio"}:
        raise ValueError("Protocol must be either 'sse' or 'stdio'")
    return protocol


def require_client_settings(config_path: Path) -> dict[str, Any]:
    payload = load_json(config_path)
    protocol = normalize_protocol(str(payload.get("protocol", _DEFAULT_PROTOCOL)))
    client_key = str(payload.get("client_api_key", "")).strip()
    server_url = str(payload.get("server_url", "")).strip()
    if not client_key:
        raise ValueError(f"No client_api_key found in {config_path}")
    if protocol == "sse" and not server_url:
        raise ValueError(f"No server_url found in {config_path}")
    payload["protocol"] = protocol
    return payload


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
                continue
            key, _, value = raw_line.partition("=")
            payload[key.strip()] = value.strip()
    except Exception:
        pass
    return payload


def load_server_release_metadata(install_dir: Path) -> dict[str, Any]:
    from .common import load_json
    path = install_dir / ".minder-release.json"
    return load_json(path)
