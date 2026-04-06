"""
BM25 + Vector hybrid retrieval.

Combines normalised BM25 keyword scores with normalised vector similarity
scores using a configurable alpha blend:

    combined = alpha * vector_score + (1 - alpha) * bm25_score

alpha = 1.0  →  pure vector search
alpha = 0.0  →  pure BM25
alpha = 0.5  →  equal blend (default)

BM25 is implemented in pure Python (no external index server required).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# BM25 helpers
# ---------------------------------------------------------------------------

_BM25_K1 = 1.5
_BM25_B = 0.75


def _tokenize(text: str) -> list[str]:
    return [tok for tok in text.lower().split() if len(tok) > 1]


def _bm25_score(
    query_terms: list[str],
    doc_tokens: list[str],
    doc_freq: dict[str, int],
    num_docs: int,
    avg_dl: float,
) -> float:
    dl = len(doc_tokens)
    tf_map: Counter[str] = Counter(doc_tokens)
    score = 0.0
    for term in query_terms:
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf_norm = (tf * (_BM25_K1 + 1.0)) / (
            tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / max(avg_dl, 1.0))
        )
        score += idf * tf_norm
    return score


def _min_max_normalize(scores: list[float]) -> list[float]:
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if math.isclose(hi, lo):
        return [1.0] * len(scores)
    span = hi - lo
    return [(s - lo) / span for s in scores]


# ---------------------------------------------------------------------------
# HybridRetriever
# ---------------------------------------------------------------------------


class HybridRetriever:
    """
    Merge vector-search results with BM25 scores computed over a corpus.

    Args:
        alpha: blend coefficient in [0, 1].
            1.0 = pure vector, 0.0 = pure BM25.
    """

    def __init__(self, alpha: float = 0.5) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be in [0.0, 1.0], got {alpha}")
        self._alpha = alpha

    @property
    def alpha(self) -> float:
        return self._alpha

    def merge(
        self,
        query: str,
        vector_results: list[dict[str, Any]],
        corpus: list[dict[str, Any]],
        *,
        limit: int = 5,
        content_key: str = "content",
        id_key: str = "path",
    ) -> list[dict[str, Any]]:
        """
        Merge *vector_results* with BM25 scores computed over *corpus*.

        Args:
            query: original user query (used for BM25 term matching).
            vector_results: documents returned by vector search, each with a
                ``"score"`` field (float, already normalised or raw cosine).
            corpus: the full candidate set to build the BM25 index over.
                Should include all docs in *vector_results* plus any extra
                candidates.  May equal *vector_results* when no corpus is
                separately available.
            limit: maximum number of merged results to return.
            content_key: key in each doc dict that holds the text content.
            id_key: key used to de-duplicate documents across the two lists.

        Returns:
            Merged, sorted list of doc dicts enriched with ``"score"``,
            ``"vector_score"``, and ``"bm25_score"`` fields.
        """
        all_docs = corpus if corpus else vector_results
        if not all_docs:
            return []

        # ---- BM25 index ----
        tokenized = [_tokenize(str(doc.get(content_key, ""))) for doc in all_docs]
        avg_dl = sum(len(t) for t in tokenized) / max(len(tokenized), 1)
        doc_freq: Counter[str] = Counter()
        for tokens in tokenized:
            for term in set(tokens):
                doc_freq[term] += 1

        query_terms = _tokenize(query)
        raw_bm25 = [
            _bm25_score(query_terms, tokens, doc_freq, len(all_docs), avg_dl)
            for tokens in tokenized
        ]
        bm25_norm = _min_max_normalize(raw_bm25)
        bm25_map: dict[str, float] = {
            str(doc.get(id_key, i)): bm25_norm[i]
            for i, doc in enumerate(all_docs)
        }

        # ---- Vector score map ----
        raw_vec = [float(doc.get("score", 0.0)) for doc in vector_results]
        vec_norm = _min_max_normalize(raw_vec)
        vec_map: dict[str, float] = {
            str(doc.get(id_key, i)): vec_norm[i]
            for i, doc in enumerate(vector_results)
        }

        # ---- Union merge ----
        vec_ids = {str(doc.get(id_key, "")) for doc in vector_results}
        candidates = list(vector_results) + [
            doc for doc in all_docs
            if str(doc.get(id_key, "")) not in vec_ids
        ]

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for doc in candidates:
            key = str(doc.get(id_key, id(doc)))
            if key in seen:
                continue
            seen.add(key)
            v = vec_map.get(key, 0.0)
            b = bm25_map.get(key, 0.0)
            combined = round(self._alpha * v + (1.0 - self._alpha) * b, 6)
            merged.append(
                {
                    **doc,
                    "score": combined,
                    "vector_score": round(v, 6),
                    "bm25_score": round(b, 6),
                }
            )

        merged.sort(key=lambda d: float(d["score"]), reverse=True)
        return merged[:limit]
