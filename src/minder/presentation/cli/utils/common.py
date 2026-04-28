from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_DEFAULT_SERVER_URL = "http://localhost:8800/sse"
_DEFAULT_PROTOCOL = "sse"
_DEFAULT_RELEASE_REPOSITORY_URL = "https://github.com/hiimtrung/minder"


def client_config_path() -> Path:
    return Path.home() / ".minder" / "client.json"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def marker_pair(path: Path, key: str) -> tuple[str, str]:
    if path.name == ".gitignore":
        return (f"# minder:begin {key}", f"# minder:end {key}")
    return (f"<!-- minder:begin {key} -->", f"<!-- minder:end {key} -->")


def wrap_managed_block(path: Path, key: str, body: str) -> str:
    start, end = marker_pair(path, key)
    normalized_body = body.strip("\n")
    return f"{start}\n{normalized_body}\n{end}\n"


def upsert_managed_block(path: Path, key: str, body: str) -> None:
    block = wrap_managed_block(path, key, body)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    start, end = marker_pair(path, key)
    if start in existing and end in existing:
        before, remainder = existing.split(start, 1)
        _, after = remainder.split(end, 1)
        updated = before.rstrip()
        if updated:
            updated += "\n\n"
        updated += block.rstrip("\n")
        tail = after.strip("\n")
        if tail:
            updated += "\n\n" + tail
        updated += "\n"
    else:
        updated = existing.rstrip("\n")
        if updated:
            updated += "\n\n"
        updated += block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def remove_managed_block(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    existing = path.read_text(encoding="utf-8")
    start, end = marker_pair(path, key)
    if start not in existing or end not in existing:
        return False
    before, remainder = existing.split(start, 1)
    _, after = remainder.split(end, 1)
    updated = before.rstrip("\n")
    tail = after.strip("\n")
    if updated and tail:
        updated = f"{updated}\n\n{tail}\n"
    elif updated:
        updated = f"{updated}\n"
    elif tail:
        updated = f"{tail}\n"
    else:
        updated = ""
    if updated:
        path.write_text(updated, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return True


def appdata_dir() -> Path:
    if platform.system() == "Windows":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "minder"
    return Path.home() / ".minder"


def base_http_url(server_url: str) -> str:
    parts = urlsplit(server_url)
    # Rebuild without path/query/fragment to get the base
    from urllib.parse import urlunsplit
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def sse_url(server_url: str) -> str:
    base = base_http_url(server_url)
    return f"{base.rstrip('/')}/sse"


def mcp_url(server_url: str) -> str:
    base = base_http_url(server_url)
    return f"{base.rstrip('/')}/mcp"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple shell-style .env file into a dictionary."""
    if not path.is_file():
        return {}
    env: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key:
                env[key] = val
    except Exception:
        pass
    return env
