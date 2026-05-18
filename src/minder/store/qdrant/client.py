"""
Qdrant Client — thin wrapper around qdrant_client.AsyncQdrantClient.

Manages connection lifecycle and provides a shared client instance.
"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient


class QdrantClientWrapper:
    """Reusable Qdrant client wrapper."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        *,
        api_key: str | None = None,
        prefer_grpc: bool = False,
        prefix: str = "minder_",
    ) -> None:
        self._url = url
        self._prefix = prefix
        self.client = AsyncQdrantClient(
            url=url,
            api_key=api_key or None,
            prefer_grpc=prefer_grpc,
            check_compatibility=False,
        )

    @property
    def prefix(self) -> str:
        return self._prefix

    def collection_name(self, name: str) -> str:
        """Return a prefixed collection name."""
        return f"{self._prefix}{name}"

    async def close(self) -> None:
        await self.client.close()
