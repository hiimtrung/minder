"""
RerankerNode — re-ranks state.retrieved_docs into state.reranked_docs.

Runtime strategy (tried in order):
  1. ``sentence_transformers.CrossEncoder`` — if the package is installed and
     the model loads successfully.
  2. MMR with document embeddings — if an ``embedding_provider`` is supplied.
  3. Passthrough — sort by existing score, no re-scoring.

The node always writes ``state.reranked_docs`` and records
``state.metadata["reranker_runtime"]`` with the strategy used.
"""

from __future__ import annotations

from typing import Any

from minder.embedding.base import EmbeddingProvider
from minder.graph.state import GraphState
from minder.retrieval.mmr import mmr_rerank
from minder.runtime import load_attr, module_available


class RerankerNode:
    """
    Args:
        top_k: maximum number of documents to keep after re-ranking.
        lambda_mult: MMR trade-off (0 = max diversity, 1 = max relevance).
        cross_encoder_model: HuggingFace model id used when
            ``sentence_transformers`` is available.
        embedding_provider: optional embedder used for MMR fallback.
    """

    def __init__(
        self,
        *,
        top_k: int = 5,
        lambda_mult: float = 0.5,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._top_k = top_k
        self._lambda_mult = lambda_mult
        self._cross_encoder_model = cross_encoder_model
        self._embedding_provider = embedding_provider
        self._cross_encoder: Any | None = None

    # ------------------------------------------------------------------
    # Runtime detection
    # ------------------------------------------------------------------

    @property
    def runtime(self) -> str:
        if module_available("sentence_transformers"):
            return "cross_encoder"
        if self._embedding_provider is not None:
            return "mmr"
        return "passthrough"

    def _load_cross_encoder(self) -> Any | None:
        if self._cross_encoder is not None:
            return self._cross_encoder
        ce_cls = load_attr("sentence_transformers", "CrossEncoder")
        if ce_cls is None:
            return None
        try:
            self._cross_encoder = ce_cls(self._cross_encoder_model)
        except Exception:  # noqa: BLE001
            return None
        return self._cross_encoder

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, state: GraphState) -> GraphState:
        docs = list(state.retrieved_docs)
        if not docs:
            state.reranked_docs = []
            state.metadata["reranker_runtime"] = "passthrough"
            return state

        # ---- Strategy 1: cross-encoder ----
        ce = self._load_cross_encoder()
        if ce is not None:
            reranked = self._run_cross_encoder(ce, state.query, docs)
            if reranked is not None:
                state.reranked_docs = reranked
                state.metadata["reranker_runtime"] = "cross_encoder"
                return state

        # ---- Strategy 2: MMR with embeddings ----
        if self._embedding_provider is not None:
            state.reranked_docs = self._run_mmr(state.query, docs)
            state.metadata["reranker_runtime"] = "mmr"
            return state

        # ---- Strategy 3: passthrough (score sort) ----
        state.reranked_docs = sorted(
            docs, key=lambda d: float(d.get("score", 0.0)), reverse=True
        )[: self._top_k]
        state.metadata["reranker_runtime"] = "passthrough"
        return state

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_cross_encoder(
        self, ce: Any, query: str, docs: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        try:
            pairs = [[query, str(doc.get("content", ""))] for doc in docs]
            scores = ce.predict(pairs)
            scored = [
                {**doc, "score": float(score)}
                for doc, score in zip(docs, scores, strict=False)
            ]
            scored.sort(key=lambda d: float(d["score"]), reverse=True)
            return scored[: self._top_k]
        except Exception:  # noqa: BLE001
            return None

    def _run_mmr(self, query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        assert self._embedding_provider is not None  # guarded by caller
        query_emb = self._embedding_provider.embed(query)
        enriched: list[dict[str, Any]] = []
        for doc in docs:
            d = dict(doc)
            if not isinstance(d.get("embedding"), list):
                # Embed truncated content to stay within model context
                d["embedding"] = self._embedding_provider.embed(
                    str(d.get("content", ""))[:512]
                )
            enriched.append(d)
        return mmr_rerank(
            query_emb,
            enriched,
            top_k=self._top_k,
            lambda_mult=self._lambda_mult,
        )
