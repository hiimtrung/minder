from __future__ import annotations

import logging
from importlib.metadata import (
    PackageNotFoundError,
    version as package_version,
)

import httpx

logger = logging.getLogger(__name__)

_PYPI_JSON_URL = "https://pypi.org/pypi/minder/json"


def parse_version(raw_version: str) -> tuple[int, ...]:
    normalized = raw_version.strip().lstrip("v")
    parts: list[int] = []
    for piece in normalized.split("."):
        digits = "".join(char for char in piece if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def installed_package_version() -> str | None:
    try:
        return package_version("minder")
    except PackageNotFoundError:
        return None


def latest_pypi_version() -> str | None:
    try:
        response = httpx.get(_PYPI_JSON_URL, timeout=3)
        response.raise_for_status()
    except Exception:
        return None
    payload = response.json()
    info = payload.get("info", {}) if isinstance(payload, dict) else {}
    version_value = info.get("version")
    if not isinstance(version_value, str) or not version_value.strip():
        return None
    return version_value.strip()


def cli_update_available() -> tuple[str | None, str | None, bool]:
    installed = installed_package_version()
    latest = latest_pypi_version()
    if installed is None or latest is None:
        return installed, latest, False
    return installed, latest, parse_version(latest) > parse_version(installed)


def maybe_print_upgrade_notice() -> None:
    installed = installed_package_version()
    latest = latest_pypi_version()
    if installed is None or latest is None:
        return
    if parse_version(latest) <= parse_version(installed):
        return
    print(
        f"A newer minder CLI is available ({installed} -> {latest}). "
        "Run 'uv tool upgrade minder' or 'pipx upgrade minder'."
    )


def bootstrap_version() -> str:
    return installed_package_version() or "dev"
