"""
Text chunking with markdown-heading awareness.

Splits documents by heading boundaries first, then applies a sliding-window
fallback for sections that exceed chunk_size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


@dataclass
class TextChunk:
    content: str
    start_char: int
    end_char: int


class TextSplitter:
    """
    Markdown-aware sliding-window text chunker.

    Args:
        chunk_size: target chunk length in characters (default 512 ≈ ~128 tokens).
        overlap: character overlap between adjacent window chunks (default 64).
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError(
                f"overlap must be in [0, chunk_size), got overlap={overlap} chunk_size={chunk_size}"
            )
        self._chunk_size = chunk_size
        self._overlap = overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(self, text: str) -> list[TextChunk]:
        """
        Split *text* into chunks.

        Strategy:
        1. Attempt a split at markdown heading boundaries.
        2. Any resulting section that still exceeds chunk_size is
           sub-split using a sliding window.
        3. If no headings are found the whole text goes through the
           sliding window directly.

        Returns:
            Ordered list of :class:`TextChunk` objects.
        """
        if not text:
            return []

        heading_sections = self._split_at_headings(text)
        if len(heading_sections) > 1:
            result: list[TextChunk] = []
            for section in heading_sections:
                if len(section.content) <= self._chunk_size:
                    result.append(section)
                else:
                    result.extend(
                        self._sliding_window(section.content, char_offset=section.start_char)
                    )
            return result

        return self._sliding_window(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _split_at_headings(text: str) -> list[TextChunk]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return [TextChunk(content=text, start_char=0, end_char=len(text))]

        chunks: list[TextChunk] = []

        # Content before the first heading
        first_heading_start = matches[0].start()
        if first_heading_start > 0:
            pre = text[:first_heading_start].strip()
            if pre:
                chunks.append(
                    TextChunk(content=pre, start_char=0, end_char=first_heading_start)
                )

        # Each heading section: from heading start to next heading start (or EOF)
        boundaries = [m.start() for m in matches] + [len(text)]
        for i in range(len(boundaries) - 1):
            start, end = boundaries[i], boundaries[i + 1]
            content = text[start:end].strip()
            if content:
                chunks.append(TextChunk(content=content, start_char=start, end_char=end))

        return chunks or [TextChunk(content=text, start_char=0, end_char=len(text))]

    def _sliding_window(self, text: str, *, char_offset: int = 0) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        step = self._chunk_size - self._overlap
        pos = 0
        while pos < len(text):
            end = min(pos + self._chunk_size, len(text))
            content = text[pos:end]
            if content.strip():
                chunks.append(
                    TextChunk(
                        content=content,
                        start_char=char_offset + pos,
                        end_char=char_offset + end,
                    )
                )
            if end == len(text):
                break
            pos += step

        if not chunks and text.strip():
            chunks.append(
                TextChunk(
                    content=text,
                    start_char=char_offset,
                    end_char=char_offset + len(text),
                )
            )
        return chunks
