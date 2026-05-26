from __future__ import annotations

from datetime import datetime


def _iso(dt: datetime | str | None) -> str | None:
    """Return an ISO-8601 string from either a datetime or an already-formatted string."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()
