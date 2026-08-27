from __future__ import annotations

import re
import uuid
from typing import Literal
from minder.domain.models import Contract


class ContractExtractor:
    """Extracts API Routes, DTO Schemas, gRPC/Protobuf definitions from source code."""

    _ROUTE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
        "python": [re.compile(r"""@(?:router|app)\.(get|post|put|delete|patch|options|head)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE)],
        "typescript": [re.compile(r"""(?:router|app)\.(get|post|put|delete|patch|options|head)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE)],
        "javascript": [re.compile(r"""(?:router|app)\.(get|post|put|delete|patch|options|head)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE)],
        "go": [re.compile(r"""\.(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*\(\s*["']([^"']+)["']""", re.IGNORECASE)],
        "rust": [re.compile(r"""#\[(?:get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']\s*\)\]""", re.IGNORECASE)],
        "java": [re.compile(r"""@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']""", re.IGNORECASE)],
    }

    _SCHEMA_PATTERNS: dict[str, list[tuple[re.Pattern[str], ContractKind]]] = {
        "python": [
            (re.compile(r"^class\s+([A-Za-z0-9_]+)\s*\((?:BaseModel|TypedDict|object)?\)\s*:", re.MULTILINE), "dto_schema"),
        ],
        "typescript": [
            (re.compile(r"^(?:export\s+)?(?:interface|type)\s+([A-Za-z0-9_]+)\s*(?:=|\{)", re.MULTILINE), "dto_schema"),
        ],
        "javascript": [
            (re.compile(r"^(?:export\s+)?(?:class)\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE), "dto_schema"),
        ],
        "go": [
            (re.compile(r"^type\s+([A-Za-z0-9_]+)\s+struct\s*\{", re.MULTILINE), "dto_schema"),
        ],
        "rust": [
            (re.compile(r"^(?:pub\s+)?(?:struct|enum)\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE), "dto_schema"),
        ],
        "java": [
            (re.compile(r"^(?:public\s+)?(?:class|record)\s+([A-Za-z0-9_]+)(?:\s*\{|\s*\()", re.MULTILINE), "dto_schema"),
        ],
        "protobuf": [
            (re.compile(r"^message\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE), "dto_schema"),
            (re.compile(r"^\s*rpc\s+([A-Za-z0-9_]+)\s*\(([^)]+)\)\s*returns\s*\(([^)]+)\)", re.MULTILINE), "grpc_method"),
        ],
    }

    def extract(
        self,
        *,
        code: str,
        file_path: str,
        language: str,
        workspace_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        lines = code.splitlines()
        lang = language.lower()
        if lang in {"ts", "tsx", "astro"}:
            lang = "typescript"
        elif lang in {"js", "jsx"}:
            lang = "javascript"
        elif lang in {"py"}:
            lang = "python"
        elif lang in {"rs"}:
            lang = "rust"
        elif lang in {"proto", "proto3"}:
            lang = "protobuf"

        # 1. Extract HTTP Routes for this language
        route_patterns = self._ROUTE_PATTERNS.get(lang, [])
        for pattern in route_patterns:
            for i, line in enumerate(lines):
                match = pattern.search(line)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    identifier = f"{method} {path}"
                    
                    end_idx = min(i + 15, len(lines))
                    raw_def = "\n".join(lines[i:end_idx]).strip()

                    contracts.append(
                        Contract(
                            id=uuid.uuid4(),
                            workspace_id=workspace_id,
                            repo_id=repo_id,
                            kind="http_route",
                            identifier=identifier,
                            raw_definition=raw_def,
                            source_file=file_path,
                            start_line=i + 1,
                            end_line=end_idx,
                            language=language,
                            metadata={"method": method, "path": path},
                        )
                    )

        # 2. Extract Schemas / DTOs / RPCs for this language
        schema_patterns = self._SCHEMA_PATTERNS.get(lang, [])
        for pattern, kind in schema_patterns:
            for match in pattern.finditer(code):
                name = match.group(1)
                start_char = match.start()
                start_line = code.count("\n", 0, start_char) + 1

                end_line = min(start_line + 20, len(lines))
                raw_def = "\n".join(lines[start_line - 1 : end_line]).strip()

                identifier = f"rpc {name}" if kind == "grpc_method" else name

                contracts.append(
                    Contract(
                        id=uuid.uuid4(),
                        workspace_id=workspace_id,
                        repo_id=repo_id,
                        kind=kind,
                        identifier=identifier,
                        raw_definition=raw_def,
                        source_file=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        language=language,
                        metadata={"symbol_name": name},
                    )
                )

        return contracts
