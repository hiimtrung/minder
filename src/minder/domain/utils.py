from __future__ import annotations

from datetime import datetime


def _iso(dt: datetime | str | None) -> str | None:
    """Return an ISO-8601 string from either a datetime or an already-formatted string.

    Qdrant stores all datetimes as ISO strings in its JSON payload; other backends
    (SQLAlchemy, MongoDB) may return actual datetime objects. This helper normalises
    both so callers don't need to care which backend is active.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()
