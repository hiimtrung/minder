"""
Multi-language AST and Syntax-Aware Code Splitter.
Supports Python, TypeScript, JavaScript, Java, Go, Rust, C++, Astro, HTML, CSS, SCSS, YAML, JSON, TOML.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    content: str               # Complete, self-contained chunk text
    start_line: int            # 1-indexed start line in original source
    end_line: int              # 1-indexed end line in original source
    symbol_name: str | None    # Function, Struct, Class, Interface name, or None
    language: str
    imports: str = field(default="")


class CodeSplitter:
    """Split source code and config files into semantic chunks."""

    _TOP_LEVEL_PATTERNS = {
        "typescript": re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class|interface|type|enum|const)\s+([A-Za-z0-9_$]+)"),
        "javascript": re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class|const|let|var)\s+([A-Za-z0-9_$]+)"),
        "go": re.compile(r"^(func|type)\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)"),
        "rust": re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?(fn|struct|enum|trait|impl|type)\s+([A-Za-z0-9_]+)"),
        "java": re.compile(r"^(?:public|protected|private|static|final|abstract|\s)*\s*(class|interface|enum|record)\s+([A-Za-z0-9_]+)"),
        "cpp": re.compile(r"^(?:class|struct|enum|namespace|void|int|bool|auto|[A-Za-z0-9_:]+)\s+([A-Za-z0-9_:]+)\s*(?:\(.*\)|{)"),
        "c": re.compile(r"^(?:struct|enum|void|int|char|float|double|[A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s*(?:\(.*\)|{)"),
    }

    def split(self, code: str, language: str = "python") -> list[CodeChunk]:
        if not code or not code.strip():
            return []

        lang = language.lower().strip()
        if lang in {"py", "python"}:
            return self._split_python(code)
        if lang in {"ts", "typescript", "tsx", "js", "javascript", "jsx", "go", "golang", "rust", "rs", "java", "cpp", "c", "cxx", "astro"}:
            return self._split_brace_languages(code, language=lang)
        if lang in {"yaml", "yml", "json", "toml", "html", "css", "scss"}:
            return self._split_text_blocks(code, language=lang)

        # Fallback: try Python AST first, then brace-based
        try:
            return self._split_python(code)
        except SyntaxError:
            return self._split_brace_languages(code, language=lang)

    # ------------------------------------------------------------------
    # Python (AST-aware)
    # ------------------------------------------------------------------

    def _split_python(self, code: str) -> list[CodeChunk]:
        lines = code.splitlines(keepends=True)
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return [CodeChunk(content=code.strip(), start_line=1, end_line=len(lines), symbol_name=None, language="python")]

        import_lines: list[str] = []
        top_symbols: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                s = node.lineno - 1
                e = getattr(node, "end_lineno", node.lineno) - 1
                import_lines.extend(lines[s : e + 1])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_symbols.append(node)

        imports_str = "".join(import_lines).rstrip()

        if not top_symbols:
            return [
                CodeChunk(
                    content=code.strip(),
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
            body = "".join(lines[start : end + 1]).rstrip()
            content = f"{imports_str}\n\n{body}".strip() if imports_str else body
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
    # Brace Languages (TypeScript, Go, Rust, Java, C++, Astro, etc.)
    # ------------------------------------------------------------------

    def _split_brace_languages(self, code: str, language: str) -> list[CodeChunk]:
        lines = code.splitlines(keepends=True)
        normalized_lang = "typescript" if language in {"ts", "typescript", "tsx", "js", "javascript", "jsx", "astro"} else language
        pattern = self._TOP_LEVEL_PATTERNS.get(normalized_lang)

        chunks: list[CodeChunk] = []
        depth = 0
        chunk_start = 0
        current_symbol: str | None = None
        header_lines: list[str] = []

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            
            # Detect package / imports header before first top-level symbol
            if not chunks and depth == 0 and (line.startswith(("import ", "package ", "using ", "use ", "from ", "#include")) or not line):
                header_lines.append(raw_line)
                chunk_start = i + 1
                continue

            # Detect top-level declaration at depth 0
            if depth == 0 and pattern and pattern.match(line):
                match = pattern.match(line)
                if match:
                    current_symbol = match.group(2) if len(match.groups()) >= 2 else match.group(1)

            depth += raw_line.count("{") - raw_line.count("}")
            if depth < 0:
                depth = 0

            # End of a top-level block
            if depth == 0 and i >= chunk_start:
                body = "".join(lines[chunk_start : i + 1]).strip()
                if body and len(body) > 10:
                    header_str = "".join(header_lines).strip()
                    full_content = f"{header_str}\n\n{body}".strip() if header_str and not body.startswith(header_str) else body
                    chunks.append(
                        CodeChunk(
                            content=full_content,
                            start_line=chunk_start + 1,
                            end_line=i + 1,
                            symbol_name=current_symbol,
                            language=language,
                            imports=header_str,
                        )
                    )
                chunk_start = i + 1
                current_symbol = None

        # Remaining lines
        if chunk_start < len(lines):
            body = "".join(lines[chunk_start:]).strip()
            if body and len(body) > 10:
                chunks.append(
                    CodeChunk(
                        content=body,
                        start_line=chunk_start + 1,
                        end_line=len(lines),
                        symbol_name=None,
                        language=language,
                    )
                )

        if not chunks:
            return [CodeChunk(content=code.strip(), start_line=1, end_line=len(lines), symbol_name=None, language=language)]

        return chunks

    # ------------------------------------------------------------------
    # Config & Markup Files (YAML, JSON, TOML, HTML, CSS)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text_blocks(code: str, language: str) -> list[CodeChunk]:
        lines = code.splitlines(keepends=True)
        if len(lines) <= 50:
            return [CodeChunk(content=code.strip(), start_line=1, end_line=len(lines), symbol_name=None, language=language)]

        # Split large config/markup files into ~50-line logical chunks
        chunks: list[CodeChunk] = []
        chunk_size = 40
        for i in range(0, len(lines), chunk_size):
            end_idx = min(i + chunk_size, len(lines))
            body = "".join(lines[i:end_idx]).strip()
            if body:
                chunks.append(
                    CodeChunk(
                        content=body,
                        start_line=i + 1,
                        end_line=end_idx,
                        symbol_name=f"section_{i // chunk_size + 1}",
                        language=language,
                    )
                )
        return chunks
