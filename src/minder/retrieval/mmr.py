"""
Maximal Marginal Relevance (MMR) diversity re-ranking.

MMR balances relevance to the query against redundancy among already-selected
results.  lambda_mult controls the trade-off:
  lambda_mult = 1.0  →  pure relevance ranking  (no diversity)
  lambda_mult = 0.0  →  maximum diversity        (no relevance)
  lambda_mult = 0.5  →  balanced default

Reference: Carbonell & Goldstein (1998) "The Use of MMR, Diversity-Based
           Reranking for Reordering Documents and Producing Summaries"
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _relevance(doc: dict[str, Any], query_embedding: list[float], embedding_key: str, score_key: str) -> float:
    emb = doc.get(embedding_key)
    if isinstance(emb, list) and emb:
        return _cosine(query_embedding, emb)
    return float(doc.get(score_key, 0.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mmr_rerank(
    query_embedding: list[float],
    candidates: list[dict[str, Any]],
    *,
    top_k: int = 5,
    lambda_mult: float = 0.5,
    embedding_key: str = "embedding",
    score_key: str = "score",
) -> list[dict[str, Any]]:
    """
    Re-rank *candidates* using Maximal Marginal Relevance.

    Args:
        query_embedding: embedding vector of the query.
        candidates: list of document dicts, each optionally containing an
            ``embedding_key`` field (list[float]) and/or a ``score_key``
            field (float).  Documents without embeddings fall back to their
            existing score for relevance estimation.
        top_k: maximum number of results to return.
        lambda_mult: trade-off coefficient in [0, 1].
        embedding_key: key in each doc dict that holds the document embedding.
        score_key: key used as a relevance proxy when no embedding is present.

    Returns:
        A sub-list of *candidates* of length ≤ top_k, ordered by MMR score.
    """
    if not candidates:
        return []

    top_k = max(1, top_k)
    lambda_mult = max(0.0, min(1.0, lambda_mult))

    # Pre-compute relevance scores to avoid repeated cosine calls.
    relevances = [
        _relevance(doc, query_embedding, embedding_key, score_key)
        for doc in candidates
    ]

    selected_indices: list[int] = []
    remaining_indices = list(range(len(candidates)))

    while remaining_indices and len(selected_indices) < top_k:
        best_score = -float("inf")
        best_pos = 0

        for pos, idx in enumerate(remaining_indices):
            rel = relevances[idx]

            if not selected_indices:
                mmr_score = rel
            else:
                doc_emb = candidates[idx].get(embedding_key)
                if isinstance(doc_emb, list) and doc_emb:
                    max_sim = max(
                        _cosine(doc_emb, candidates[sel].get(embedding_key) or [])
                        for sel in selected_indices
                    )
                else:
                    max_sim = 0.0
                mmr_score = lambda_mult * rel - (1.0 - lambda_mult) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_pos = pos

        chosen = remaining_indices.pop(best_pos)
        selected_indices.append(chosen)

    return [candidates[i] for i in selected_indices]
