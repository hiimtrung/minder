"""
MongoDB Async Client — Motor singleton with connection pooling.

Usage:
    client = MongoClient(uri="mongodb://localhost:27017", database="minder")
    db = client.db
    await client.health_check()
    await client.close()
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


class MongoClient:
    """Thin wrapper around Motor's async client with lifecycle helpers."""

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        database: str = "minder",
        *,
        min_pool_size: int = 5,
        max_pool_size: int = 50,
    ) -> None:
        self._client: AsyncIOMotorClient = AsyncIOMotorClient(  # type: ignore[type-arg]
            uri,
            minPoolSize=min_pool_size,
            maxPoolSize=max_pool_size,
            serverSelectionTimeoutMS=5000,
        )
        self._db: AsyncIOMotorDatabase = self._client[database]  # type: ignore[type-arg]

    @property
    def db(self) -> AsyncIOMotorDatabase:  # type: ignore[type-arg]
        return self._db

    async def health_check(self) -> bool:
        """Ping the MongoDB server."""
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Motor client."""
        self._client.close()
