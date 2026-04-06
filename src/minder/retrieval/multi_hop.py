"""
Multi-hop retrieval.

Iteratively refines the search query using content from the previous hop's
top result, then merges and de-duplicates results across all hops.

Hop 1 → retrieve on original query
Hop 2 → expand query with key terms extracted from hop-1 top result → retrieve
...
Final → merge all hops, sort by score, return top-K.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Retriever protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrieveFn(Protocol):
    """Any async callable ``(query, *, limit) → list[dict]`` qualifies."""

    async def __call__(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# MultiHopRetriever
# ---------------------------------------------------------------------------


class MultiHopRetriever:
    """
    Iterative retrieval that uses the top result from each hop to expand the
    query for the next hop.

    Args:
        retrieve_fn: async callable matching :class:`RetrieveFn`.
        max_hops: total number of retrieval hops (default 2).
    """

    def __init__(self, retrieve_fn: RetrieveFn, *, max_hops: int = 2) -> None:
        self._retrieve_fn = retrieve_fn
        self._max_hops = max(1, max_hops)

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Run multi-hop retrieval.

        Returns:
            Deduplicated, score-sorted list of documents across all hops,
            truncated to *limit*.  Each document gains a ``"hop"`` metadata
            field indicating which hop first found it.
        """
        seen_keys: set[str] = set()
        all_results: list[dict[str, Any]] = []
        current_query = query

        for hop in range(self._max_hops):
            hop_results = await self._retrieve_fn(current_query, limit=limit)
            new_this_hop: list[dict[str, Any]] = []
            for doc in hop_results:
                key = self._doc_key(doc)
                if key not in seen_keys:
                    seen_keys.add(key)
                    enriched = dict(doc)
                    enriched.setdefault("hop", hop + 1)
                    all_results.append(enriched)
                    new_this_hop.append(enriched)

            # Expand query for next hop using key terms from top new result
            if hop < self._max_hops - 1 and new_this_hop:
                top_content = str(new_this_hop[0].get("content", ""))
                expansion = self._expand_query(top_content, base_query=query)
                if expansion:
                    current_query = f"{query} {expansion}"

        # Sort by descending score then stable insertion order
        all_results.sort(key=lambda d: float(d.get("score", 0.0)), reverse=True)
        return all_results[:limit]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _doc_key(doc: dict[str, Any]) -> str:
        return str(doc.get("path", doc.get("id", id(doc))))

    @staticmethod
    def _expand_query(content: str, *, base_query: str, max_terms: int = 5) -> str:
        """Extract high-frequency content terms not already in the base query."""
        base_tokens = set(base_query.lower().split())
        tokens = [
            tok
            for tok in content.lower().split()
            if len(tok) > 3 and tok not in base_tokens and tok.isalpha()
        ]
        freq: Counter[str] = Counter(tokens)
        top_terms = [term for term, _ in freq.most_common(max_terms)]
        return " ".join(top_terms)
