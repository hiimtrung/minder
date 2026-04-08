"""
AST-aware code chunking.

Python: uses the standard-library ``ast`` module to split at top-level
  ``def`` / ``async def`` / ``class`` boundaries.  Module-level import
  statements are prepended to every chunk for self-containedness.

TypeScript / JavaScript / Java: falls back to a brace-depth (``{`` / ``}``)
  line-based splitter that cuts at depth-0 boundaries.

Any other language: attempts Python AST first, then brace-depth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

PythonSymbol = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass
class CodeChunk:
    content: str          # Complete, self-contained chunk text
    start_line: int       # 1-indexed start line in the original source
    end_line: int         # 1-indexed end line in the original source
    symbol_name: str | None   # Function/class name, or None for file-level chunks
    language: str
    imports: str = field(default="")   # Module-level imports prepended to content


# ---------------------------------------------------------------------------
# CodeSplitter
# ---------------------------------------------------------------------------


class CodeSplitter:
    """
    Split source code into logical chunks.

    Usage::

        splitter = CodeSplitter()
        chunks = splitter.split(source_code, language="python")
    """

    def split(self, code: str, language: str = "python") -> list[CodeChunk]:
        """
        Split *code* into :class:`CodeChunk` objects.

        Args:
            code: source code text.
            language: one of ``"python"``, ``"typescript"``, ``"javascript"``,
                ``"ts"``, ``"js"``, ``"java"``.  Anything else is attempted as
                Python first, then falls back to brace-depth splitting.
        """
        if not code.strip():
            return []

        lang = language.lower()
        if lang == "python":
            return self._split_python(code)
        if lang in {"typescript", "ts", "javascript", "js", "java"}:
            return self._split_by_brace_depth(code, language=language)
        # Unknown language: try Python AST, fall back to brace split
        try:
            return self._split_python(code)
        except SyntaxError:
            return self._split_by_brace_depth(code, language=language)

    # ------------------------------------------------------------------
    # Python (AST-aware)
    # ------------------------------------------------------------------

    def _split_python(self, code: str) -> list[CodeChunk]:
        lines = code.splitlines(keepends=True)
        tree = ast.parse(code)

        import_lines: list[str] = []
        top_symbols: list[PythonSymbol] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                s = node.lineno - 1
                e = getattr(node, "end_lineno", node.lineno) - 1
                import_lines.extend(lines[s : e + 1])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_symbols.append(node)

        imports_str = "".join(import_lines).rstrip()

        # No top-level symbols → whole file is one chunk
        if not top_symbols:
            return [
                CodeChunk(
                    content=code,
                    start_line=1,
                    end_line=len(lines),
                    symbol_name=None,
                    language="python",
                    imports=imports_str,
                )
            ]

        chunks: list[CodeChunk] = []
        for node in top_symbols:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno) - 1
            body = "".join(lines[start : end + 1])
            if imports_str:
                content = imports_str + "\n\n" + body.rstrip()
            else:
                content = body.rstrip()
            chunks.append(
                CodeChunk(
                    content=content,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    symbol_name=node.name,
                    language="python",
                    imports=imports_str,
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Brace-depth (TypeScript / JavaScript / Java)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_by_brace_depth(code: str, *, language: str) -> list[CodeChunk]:
        """Split at top-level brace-balanced block boundaries (depth 0 → 1 → 0)."""
        lines = code.splitlines(keepends=True)
        chunks: list[CodeChunk] = []
        depth = 0
        chunk_start = 0

        for i, line in enumerate(lines):
            depth += line.count("{") - line.count("}")
            if depth == 0 and i >= chunk_start:
                body = "".join(lines[chunk_start : i + 1]).strip()
                if body:
                    chunks.append(
                        CodeChunk(
                            content=body,
                            start_line=chunk_start + 1,
                            end_line=i + 1,
                            symbol_name=None,
                            language=language,
                        )
                    )
                chunk_start = i + 1
            # Guard against unbalanced braces
            if depth < 0:
                depth = 0

        # Trailing content after the last depth-0 point
        if chunk_start < len(lines):
            body = "".join(lines[chunk_start:]).strip()
            if body:
                chunks.append(
                    CodeChunk(
                        content=body,
                        start_line=chunk_start + 1,
                        end_line=len(lines),
                        symbol_name=None,
                        language=language,
                    )
                )

        # Fallback: return whole file as one chunk
        if not chunks:
            return [
                CodeChunk(
                    content=code,
                    start_line=1,
                    end_line=len(lines),
                    symbol_name=None,
                    language=language,
                )
            ]

        return chunks
