# CLAUDE.md — Technical Guidelines For Claude Code & AI Agents

This document provides operational rules, execution commands, and mandatory engineering standards for developing the **Minder** project.

---

## 1. Core Engineering Rules

1. **GRILL ME WHEN UNCLEAR**: Always ask clarifying questions regarding technical requirements, schemas, and edge cases before writing code. Never guess or hallucinate context ("Zero Assumptions, Zero Hallucinations").
2. **SDD (Spec-Driven Development)**: Always specify Data Models, DTOs, and Type Definitions before implementing business logic.
3. **TDD (Test-Driven Development)**: Always write tests first (Red) -> Write minimal code to pass (Green) -> Refactor cleanly. Never submit code without automated test coverage.
4. **LEAN MCP TOOLS**: All MCP tool retrievals must complete in **< 50ms**. FORBIDDEN to execute LangGraph chains or nested LLM inference loops inside retrieval tools (`minder_memory_recall`, `minder_skill_recall`, `minder_session_boot`, `minder_search_code`).
5. **STANDARDIZED MODEL**: Use **Qwen3.5 2B (GGUF Q4_K_M)** for local LLM to avoid sliding window attention memory leaks present in Gemma 4.
6. **LIVE CHECKLIST UPDATES**: Always update task progress in the checklist in real time as each step completes.

---

## 2. Project Architecture (Clean Architecture)

- `src/minder/domain/`: Pure Domain Entities (`Workspace`, `Repository`, `Contract`, `Memory`, `Skill`, `SessionState`, `CodeChunk`). Zero external dependencies.
- `src/minder/application/`: Use cases, Services, DTOs, and Ports/Interfaces (`IOperationalStore`, `IVectorStore`, `IGraphRepository`, `IEmbeddingProvider`, `ILLMProvider`).
- `src/minder/infrastructure/`: Infrastructure implementations (SQLite WAL, Turbovec ANN, Qwen3.5 LLM, Detached OpenAI adapter).
- `src/minder/presentation/`: Fast MCP Endpoints (SSE/Stdio), Admin REST API, CLI commands.
- `src/minder/chunking/`: AST Code Splitters (`CodeSplitter`) slicing functions, classes, and interfaces across multiple languages.
- `tests/`: Automated test suite (Unit, Integration, Concurrency, Latency Benchmarks).

---

## 3. Development & Testing Commands

```bash
# Run the Clean Architecture unit test suite
PYTHONPATH=src python3 -m unittest discover -s tests/unit -p "test_*.py"

# Run a specific unit test file
PYTHONPATH=src python3 -m unittest tests/unit/test_domain_models.py

# Type checking
mypy src/

# Linter and code formatter
ruff check src/ tests/
ruff format src/ tests/

# Start server in dev mode
python3 -m minder.server --port 8800 --dev
```

---

## 4. Documentation Standards

- All major architectural decisions must be documented in `.agents/adr/`.
- Layered technical specifications reside in `docs/architecture/` and `docs/specs/`.
- Ubiquitous domain language is defined in `CONTEXT.md`.
