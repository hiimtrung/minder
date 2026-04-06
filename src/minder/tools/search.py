from __future__ import annotations

from typing import Any

from minder.config import MinderConfig
from minder.store.interfaces import IOperationalStore
from minder.tools.memory import MemoryTools


class SearchTools:
    def __init__(self, store: IOperationalStore, config: MinderConfig) -> None:
        self._memory = MemoryTools(store, config)

    async def minder_search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return await self._memory.minder_memory_recall(query, limit=limit)
