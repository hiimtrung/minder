"""
Milvus Lite client wrapper — manages a local file-based MilvusClient instance.

MilvusClient with a .db file path auto-starts an embedded Milvus Lite instance
in-process; no external server or Docker container is required.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MilvusClientWrapper:
    """Thin wrapper around pymilvus.MilvusClient for Milvus Lite (embedded mode)."""

    def __init__(self, db_path: str = "~/.minder/data/vectors.db") -> None:
        self._db_path = str(Path(db_path).expanduser())
        self._client: object | None = None

    @property
    def client(self):  # type: ignore[return]
        if self._client is None:
            from pymilvus import MilvusClient  # type: ignore[import-untyped]
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._client = MilvusClient(self._db_path)
            logger.info("Milvus Lite started at %s", self._db_path)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._client = None
