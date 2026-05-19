"""Generic CRUD helpers for Qdrant collections."""

from __future__ import annotations
import uuid
from datetime import UTC, datetime
from typing import Any
from qdrant_client import AsyncQdrantClient, models


def _now() -> datetime:
    return datetime.now(UTC)


def _uid(v: Any) -> str:
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)


class _Doc:
    """Attribute-style wrapper for a Qdrant payload dict."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        for f in ("id", "user_id", "repo_id", "session_id", "workflow_id", "client_id"):
            val = self._data.get(f)
            if isinstance(val, str):
                try:
                    self._data[f] = uuid.UUID(val)
                except ValueError:
                    pass
        for fk in ("workflow_id", "client_id"):
            if fk not in self._data:
                self._data[fk] = None

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"Doc has no attribute '{name}'")

    def __repr__(self) -> str:
        return f"Doc({self._data!r})"


# Maximum records per scroll page. Qdrant's hard cap is 10 000; we stay below it.
_SCROLL_CAP = 9_000


class CollectionCRUD:
    """Reusable CRUD ops on a single Qdrant collection."""

    def __init__(
        self, client: AsyncQdrantClient, collection: str, vector_size: int = 4
    ) -> None:
        self._client = client
        self._collection = collection
        self._vector_size = vector_size
        self._ready = False

    async def ensure(self) -> None:
        if self._ready:
            return
        exists = await self._client.collection_exists(self._collection)
        if not exists:
            await self._client.create_collection(
                self._collection,
                vectors_config=models.VectorParams(
                    size=self._vector_size, distance=models.Distance.COSINE
                ),
            )
        self._ready = True

    async def insert(
        self, payload: dict[str, Any], point_id: str | None = None
    ) -> _Doc:
        await self.ensure()
        pid = point_id or _uid(uuid.uuid4())
        payload["id"] = pid
        payload.setdefault("created_at", _now().isoformat())
        payload.setdefault("updated_at", _now().isoformat())
        await self._client.upsert(
            self._collection,
            points=[
                models.PointStruct(
                    id=pid, vector=[0.0] * self._vector_size, payload=payload
                )
            ],
        )
        return _Doc(payload)

    async def upsert_many(
        self, records: list[tuple[str, dict[str, Any]]]
    ) -> list[_Doc]:
        await self.ensure()
        if not records:
            return []

        docs: list[dict[str, Any]] = []
        points: list[models.PointStruct] = []
        for point_id, payload in records:
            doc = dict(payload)
            doc["id"] = point_id
            doc.setdefault("created_at", _now().isoformat())
            doc["updated_at"] = _now().isoformat()
            docs.append(doc)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=[0.0] * self._vector_size,
                    payload=doc,
                )
            )

        await self._client.upsert(self._collection, points=points)
        return [_Doc(doc) for doc in docs]

    async def get(self, point_id: str) -> _Doc | None:
        await self.ensure()
        results = await self._client.retrieve(
            self._collection,
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        p = dict(results[0].payload or {})
        p["id"] = str(results[0].id)
        return _Doc(p)

    async def find_one(self, field: str, value: Any) -> _Doc | None:
        await self.ensure()
        filt = models.Filter(
            must=[
                models.FieldCondition(key=field, match=models.MatchValue(value=value))
            ]
        )
        results, _ = await self._client.scroll(
            self._collection,
            scroll_filter=filt,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        p = dict(results[0].payload or {})
        p["id"] = str(results[0].id)
        return _Doc(p)

    async def find_many(
        self,
        filters: dict[str, Any] | None = None,
        *,
        limit: int | None = 1000,
        offset: int = 0,
        order_field: str | None = None,
        order_desc: bool = True,
    ) -> list[_Doc]:
        await self.ensure()
        must: list[Any] = []
        if filters:
            for k, v in filters.items():
                if isinstance(v, bool):
                    must.append(
                        models.FieldCondition(key=k, match=models.MatchValue(value=v))
                    )
                elif isinstance(v, list):
                    must.append(
                        models.FieldCondition(key=k, match=models.MatchAny(any=v))
                    )
                else:
                    must.append(
                        models.FieldCondition(
                            key=k,
                            match=models.MatchValue(
                                value=str(v) if isinstance(v, uuid.UUID) else v
                            ),
                        )
                    )
        filt = models.Filter(must=must) if must else None

        # Qdrant scroll uses a cursor (point-ID), not a numeric offset.
        # We page through using the cursor and stop once we have enough records.
        requested = _SCROLL_CAP if limit is None else limit + offset
        need = min(requested, _SCROLL_CAP)
        all_docs: list[_Doc] = []
        cursor: Any = None
        while len(all_docs) < need:
            batch_size = min(1000, need - len(all_docs))
            points, cursor = await self._client.scroll(
                self._collection,
                scroll_filter=filt,
                limit=batch_size,
                offset=cursor,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for pt in points:
                p = dict(pt.payload or {})
                p["id"] = str(pt.id)
                all_docs.append(_Doc(p))
            if cursor is None:
                break

        if order_field:
            all_docs.sort(
                key=lambda d: d._data.get(order_field, ""), reverse=order_desc
            )
        if limit is None:
            return all_docs[offset:]
        return all_docs[offset : offset + limit]

    async def find_or(
        self, conditions: list[dict[str, Any]], *, limit: int = 1000
    ) -> list[_Doc]:
        """Return docs matching ANY of the given field=value conditions (OR semantics)."""
        await self.ensure()
        should: list[Any] = [
            models.FieldCondition(key=k, match=models.MatchValue(value=v))
            for cond in conditions
            for k, v in cond.items()
        ]
        if not should:
            return []
        filt = models.Filter(should=should)
        points, _ = await self._client.scroll(
            self._collection,
            scroll_filter=filt,
            limit=min(limit, _SCROLL_CAP),
            with_payload=True,
            with_vectors=False,
        )
        docs = []
        for pt in points:
            p = dict(pt.payload or {})
            p["id"] = str(pt.id)
            docs.append(_Doc(p))
        return docs

    async def update(self, point_id: str, updates: dict[str, Any]) -> _Doc | None:
        await self.ensure()
        existing = await self.get(point_id)
        if existing is None:
            return None
        await self.set_payload(point_id, updates)
        return await self.get(point_id)

    async def set_payload(self, point_id: str, updates: dict[str, Any]) -> None:
        await self.ensure()
        payload = dict(updates)
        payload["updated_at"] = _now().isoformat()
        await self._client.set_payload(
            self._collection, payload=payload, points=[point_id]
        )

    async def delete(self, point_id: str) -> None:
        await self.ensure()
        await self._client.delete(
            self._collection, points_selector=models.PointIdsList(points=[point_id])
        )

    async def delete_many(self, filters: dict[str, Any]) -> int:
        await self.ensure()
        must: list[Any] = []
        for k, v in filters.items():
            if isinstance(v, list):
                must.append(models.FieldCondition(key=k, match=models.MatchAny(any=v)))
            else:
                must.append(
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                )
        filt = models.Filter(must=must)
        # Collect all matching IDs via cursor pagination
        ids: list[Any] = []
        cursor: Any = None
        while True:
            points, cursor = await self._client.scroll(
                self._collection,
                scroll_filter=filt,
                limit=1000,
                offset=cursor,
                with_payload=False,
                with_vectors=False,
            )
            ids.extend(str(p.id) for p in points)
            if cursor is None or not points:
                break
        if not ids:
            return 0
        await self._client.delete(
            self._collection, points_selector=models.PointIdsList(points=ids)
        )
        return len(ids)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        await self.ensure()
        must: list[Any] = []
        if filters:
            for k, v in filters.items():
                must.append(
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                )
        filt = models.Filter(must=must) if must else None
        result = await self._client.count(self._collection, count_filter=filt)
        return result.count
