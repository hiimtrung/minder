from __future__ import annotations

import math
import uuid
from collections import Counter
from typing import Any
from typing import cast

from sqlalchemy import select

from minder.models.error import Error
from minder.store.relational import RelationalStore


class ErrorStore:
    def __init__(self, store: RelationalStore) -> None:
        self._store = store

    async def create_error(
        self,
        error_code: str,
        error_message: str,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
        resolution: str | None = None,
        embedding: list[float] | None = None,
        resolved: bool = False,
    ) -> Error:
        async with self._store._session() as sess:
            error = Error(
                id=uuid.uuid4(),
                error_code=error_code,
                error_message=error_message,
                stack_trace=stack_trace,
                context=context or {},
                resolution=resolution,
                embedding=embedding,
                resolved=resolved,
            )
            sess.add(error)
            await sess.flush()
            await sess.refresh(error)
            return error

    async def list_errors(self) -> list[Error]:
        async with self._store._session() as sess:
            result = await sess.execute(select(Error))
            return list(result.scalars().all())

    async def search_errors(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = await self.list_errors()
        query_vector = self._text_vector(query)
        ranked = []
        for row in rows:
            text = f"{row.error_code} {row.error_message} {row.context}"
            score = self._cosine_similarity(query_vector, self._text_vector(text))
            ranked.append(
                {
                    "id": row.id,
                    "error_code": row.error_code,
                    "error_message": row.error_message,
                    "resolution": row.resolution,
                    "score": round(score, 4),
                }
            )
        ranked.sort(key=lambda item: cast(float, item["score"]), reverse=True)
        return ranked[:limit]

    @staticmethod
    def _text_vector(text: str) -> Counter[str]:
        return Counter(token for token in text.lower().split() if len(token) > 2)

    @staticmethod
    def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        numerator = sum(left[key] * right[key] for key in left.keys() & right.keys())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
