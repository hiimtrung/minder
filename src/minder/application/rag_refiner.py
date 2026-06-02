from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from minder.application.continuity import _extract_json_object

if TYPE_CHECKING:
    from minder.config import MinderConfig

logger = logging.getLogger(__name__)


class RAGRefiner:
    """Post-retrieval LLM filter: verifies relevance, removes noise, returns a clean summary.

    Works on any list of items with 'id', 'title', 'content' keys.
    Falls back gracefully when the local LLM is unavailable (mock mode).
    """

    def __init__(self, config: MinderConfig) -> None:
        self._config = config
        self._llm: Any = None
        self._llm_loaded = False

    def _get_llm(self) -> Any | None:
        if not self._llm_loaded:
            self._llm_loaded = True
            try:
                from minder.llm.factory import create_llm

                llm = create_llm(self._config.llm)
                self._llm = llm if hasattr(llm, "complete_text") else None
            except Exception as exc:
                logger.debug("RAGRefiner: could not load LLM (%s), using fallback", exc)
        return self._llm

    def refine(
        self,
        *,
        query: str,
        items: list[dict[str, Any]],
        context: str | None = None,
        max_tokens: int = 800,
    ) -> tuple[list[dict[str, Any]], str]:
        """Filter retrieved items using the local LLM.

        Returns (filtered_items, summary). On any failure returns all items + a basic
        heuristic summary so callers always get a usable result.
        """
        if not items:
            return [], f"No results found for '{query}'."

        llm = self._get_llm()
        fallback_summary = self._heuristic_summary(query, items)

        if llm is None:
            return items, fallback_summary

        condensed = [
            {
                "id": str(item.get("id", str(i))),
                "title": str(item.get("title", "")),
                "snippet": str(item.get("content", ""))[:400],
                "score": round(float(item.get("score", 0.0)), 4),
                "tags": list(item.get("tags", [])),
            }
            for i, item in enumerate(items)
        ]

        prompt_lines = [
            "You are a retrieval quality filter for an AI engineering assistant.",
            "Your task: given a user query and retrieved items, keep only those that are",
            "genuinely relevant. Remove off-topic, duplicate, or vague items.",
            "",
            f"Query: {query}",
        ]
        if context:
            prompt_lines.append(f"Context: {context}")
        prompt_lines += [
            "",
            f"Items to evaluate:\n{json.dumps(condensed, ensure_ascii=False, indent=2)}",
            "",
            "Rules:",
            "- Only include an item's id in relevant_ids if it clearly helps answer the query.",
            "- If all items are relevant, include all ids.",
            "- If no items are relevant, return an empty list.",
            "- Write a concise summary (2-3 sentences) of the kept content.",
            "",
            'Return ONLY valid JSON (no markdown): {"relevant_ids": ["id1", ...], "summary": "..."}',
        ]
        prompt = "\n".join(prompt_lines)

        try:
            raw = llm.complete_text(
                prompt,
                max_tokens=max_tokens,
                temperature=min(max(self._config.llm.temperature, 0.0), 0.15),
                fallback="",
            )
        except Exception as exc:
            logger.warning("RAGRefiner LLM call failed: %s", exc)
            return items, fallback_summary

        parsed = _extract_json_object(raw)
        if not parsed:
            return items, fallback_summary

        relevant_ids = {str(rid) for rid in list(parsed.get("relevant_ids") or [])}
        summary = str(parsed.get("summary", "")).strip() or fallback_summary

        if relevant_ids:
            filtered = [item for item in items if str(item.get("id", "")) in relevant_ids]
            if not filtered:
                filtered = items
        else:
            filtered = items

        return filtered, summary

    @staticmethod
    def _heuristic_summary(query: str, items: list[dict[str, Any]]) -> str:
        titles = [str(item.get("title", "")) for item in items[:3] if item.get("title")]
        if not titles:
            return f"Retrieved {len(items)} result(s) for '{query}'."
        joined = ", ".join(titles)
        return f"Found {len(items)} result(s) for '{query}': {joined}."
