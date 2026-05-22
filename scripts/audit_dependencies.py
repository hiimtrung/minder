#!/usr/bin/env python3
"""
Dependency Direction Auditor — Clean Architecture layer boundary checker.

Verifies that imports never flow from inner layers to outer layers:
  domain/ must NOT import from application/, infrastructure/, tools/, transport/, presentation/, bootstrap/
  application/ must NOT import from tools/, transport/, presentation/, bootstrap/

Usage:
    python3 scripts/audit_dependencies.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Layer definitions (inner → outer)
# Each layer maps to its forbidden import prefixes
LAYER_RULES: dict[str, list[str]] = {
    "domain": [
        "minder.application",
        "minder.infrastructure",
        "minder.tools",
        "minder.transport",
        "minder.presentation",
        "minder.bootstrap",
        "minder.store.relational",  # concrete store implementation
        "minder.embedding.local",   # concrete embedding provider
        "minder.llm.llama_cpp",     # concrete LLM provider
        "minder.llm.openai",        # concrete LLM provider
        "minder.cache.providers",   # concrete cache provider
    ],
    "application": [
        "minder.tools",
        "minder.transport",
        "minder.presentation",
        "minder.bootstrap",
    ],
}

# Known exceptions (backward compat re-exports, composition roots)
ALLOWED_EXCEPTIONS: set[tuple[str, str]] = {
    # store/interfaces.py re-exports from domain (backward compat bridge)
    ("minder/store/interfaces.py", "minder.domain.interfaces"),
    # auth/service.py re-exports AuthError from domain
    ("minder/auth/service.py", "minder.domain.exceptions"),
    # TODO: These are pre-existing violations to be fixed when use-case
    # services are fully extracted from tools/ into application/.
    ("minder/application/admin/jobs.py", "minder.tools.skills"),
    ("minder/application/admin/use_cases.py", "minder.tools.graph"),
    ("minder/application/admin/use_cases.py", "minder.tools.registry"),
}


def get_imports(filepath: Path) -> list[str]:
    """Extract all import module names from a Python file."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def classify_layer(filepath: Path, src_root: Path) -> str | None:
    """Determine which architectural layer a file belongs to."""
    relative = filepath.relative_to(src_root / "minder")
    parts = relative.parts

    if parts[0] == "domain":
        return "domain"
    if parts[0] == "application":
        return "application"
    return None  # Not a restricted layer


def audit(src_root: Path) -> list[str]:
    """Run the dependency direction audit."""
    violations: list[str] = []

    for py_file in (src_root / "minder").rglob("*.py"):
        layer = classify_layer(py_file, src_root)
        if layer is None:
            continue

        forbidden_prefixes = LAYER_RULES.get(layer, [])
        if not forbidden_prefixes:
            continue

        relative_path = py_file.relative_to(src_root).as_posix()
        imports = get_imports(py_file)

        for imp in imports:
            for prefix in forbidden_prefixes:
                if imp.startswith(prefix):
                    key = (relative_path, imp)
                    if key in ALLOWED_EXCEPTIONS:
                        continue
                    violations.append(
                        f"  ❌ {relative_path} ({layer}) → {imp}"
                    )

    return violations


def main() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src"
    if not (src_root / "minder").is_dir():
        print(f"ERROR: Could not find minder package at {src_root / 'minder'}")
        sys.exit(1)

    print("🔍 Auditing Clean Architecture dependency directions...\n")
    violations = audit(src_root)

    if violations:
        print(f"Found {len(violations)} dependency direction violation(s):\n")
        for v in sorted(violations):
            print(v)
        print()
        sys.exit(1)
    else:
        print("✅ No dependency direction violations found!")
        sys.exit(0)


if __name__ == "__main__":
    main()
