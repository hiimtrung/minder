"""
Compacts chat history to fit within the LLM context window.

Strategy:
- Always keep the `keep_recent` most recent messages verbatim (recency bias).
- If older messages still fit in the remaining budget, keep them all.
- Otherwise drop oldest messages and prepend a single notice message so the
  LLM knows part of the history was omitted.

No LLM call is made here — this is a pure sliding-window approach so it adds
zero latency on every query.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Approximate chars-per-token for chat content (UTF-8 prose / code mix).
_CHARS_PER_TOKEN = 3


class HistoryCompactor:
    """Trims chat_history to fit within a fraction of the LLM context window."""

    def __init__(
        self,
        *,
        keep_recent: int = 6,
        history_budget_ratio: float = 0.40,
    ) -> None:
        # keep_recent: number of latest messages always preserved verbatim.
        # history_budget_ratio: fraction of context_length tokens available for history.
        self._keep_recent = keep_recent
        self._history_budget_ratio = history_budget_ratio

    def compact(
        self,
        history: list[dict[str, Any]],
        *,
        context_length: int,
    ) -> list[dict[str, Any]]:
        """Return a (possibly shorter) history list that fits within the budget.

        If messages are dropped a synthetic notice is prepended so the model
        knows earlier context exists but was truncated.
        """
        if not history:
            return []

        budget_chars = int(context_length * self._history_budget_ratio) * _CHARS_PER_TOKEN
        total_chars = sum(len(str(m.get("content", ""))) for m in history)

        if total_chars <= budget_chars:
            return history

        # Split into recent (always kept) and older (candidates for dropping).
        if len(history) > self._keep_recent:
            recent = history[-self._keep_recent :]
            older = history[: -self._keep_recent]
        else:
            recent = list(history)
            older = []

        recent_chars = sum(len(str(m.get("content", ""))) for m in recent)

        # If even the recent slice alone exceeds the budget, truncate from the
        # oldest message in that slice (keeping tail content within each message).
        if recent_chars > budget_chars:
            recent = self._fit_to_budget(recent, budget_chars)
            dropped_count = len(history) - len(recent)
            logger.warning(
                "chat_history compacted: dropped %d messages (context_length=%d)",
                dropped_count,
                context_length,
            )
            if dropped_count > 0:
                return [_notice(dropped_count)] + recent
            return recent

        # Fit as many older messages as possible within leftover budget.
        older_budget = budget_chars - recent_chars
        kept_older = self._fit_to_budget(older, older_budget)
        dropped_count = len(older) - len(kept_older)

        if dropped_count > 0:
            logger.info(
                "chat_history compacted: dropped %d older messages (context_length=%d)",
                dropped_count,
                context_length,
            )
            return [_notice(dropped_count)] + kept_older + recent

        return kept_older + recent

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_to_budget(
        messages: list[dict[str, Any]],
        budget_chars: int,
    ) -> list[dict[str, Any]]:
        """Return the maximal tail of *messages* whose total chars ≤ budget_chars."""
        kept: list[dict[str, Any]] = []
        remaining = budget_chars
        for msg in reversed(messages):
            content = str(msg.get("content", ""))
            if remaining <= 0:
                break
            if len(content) > remaining:
                # Truncate the message to fit, keeping the tail (most recent content).
                truncated = {**msg, "content": "…" + content[-(remaining - 1) :]}
                kept.insert(0, truncated)
                remaining = 0
            else:
                kept.insert(0, msg)
                remaining -= len(content)
        return kept


def _notice(dropped_count: int) -> dict[str, Any]:
    return {
        "role": "user",
        "content": (
            f"[{dropped_count} earlier message(s) omitted — context window limit reached]"
        ),
    }
