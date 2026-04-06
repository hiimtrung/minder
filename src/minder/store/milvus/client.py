"""
Milvus Client — connection wrapper.
"""

from __future__ import annotations

import asyncio
from pymilvus import MilvusClient as PyMilvusClient  # type: ignore[import-untyped]


class MilvusClient:
    """Wrapper around PyMilvus client (which is blocking, so we run it in executor if needed)."""
    
    def __init__(self, uri: str = "http://localhost:19530") -> None:
        self.uri = uri
        self.client = PyMilvusClient(uri=uri)

    async def health_check(self) -> bool:
        """Pings the Milvus server asynchronously."""
        loop = asyncio.get_running_loop()
        try:
            # We list collections as a proxy for health check
            await loop.run_in_executor(None, self.client.list_collections)
            return True
        except Exception:
            return False
