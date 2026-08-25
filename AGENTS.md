# AGENTS.md — Mandatory Technical Standards For AI Agents (Minder Project)

This document defines the core technical principles, development workflows, and discipline rules for all AI Coding Agents (Claude Code, Cursor, Windsurf, Codex, etc.) working on the **Minder** codebase.

---

## 1. Supreme Principle: Anti-Hallucination & "Grill Me" Protocol

> **ZERO ASSUMPTIONS, ZERO HALLUCINATIONS**

1. **Grill Me First**: If you encounter any ambiguous requirement, missing technical specification, missing schema, or unclear data flow across repositories/modules, **the Agent MUST STOP and interview the user ("Grill Me")**.
2. **Never Guess Payloads / Interfaces**: Never invent field names, HTTP status codes, API routes, struct fields, or configuration keys. Always read directly from source code, schema registries, or confirm with the user.
3. **Cite Concrete Evidence**: Every claim, bug report, or code change proposal must be accompanied by exact file paths and line numbers (`file:///path/to/file#L10-L25`).

---

## 2. Development Process: SDD Combined With TDD (Spec-Driven + Test-Driven)

This project strictly follows the engineering discipline from [Matt Pocock Skills](https://github.com/mattpocock/skills) (`/grill-me`, `/to-spec`, `/tdd`, `/implement`, `/verify`):

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────────────┐
│ 1. GRILL-ME  │ ──► │ 2. TO-SPEC   │ ──► │ 3. TDD (RED) │ ──► │ 4. IMPLEMENT │ ──► │ 5. VERIFY & DOCS   │
│ (Align Intent│     │ (Write Spec) │     │ (Write Test) │     │ (Write Code) │     │ (Review & Docs)    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘     └────────────────────┘
```

### Step 1: Grilling Session (`/grill-me`, `/grill-with-docs`)
- Interview the user regarding: Objectives, Edge cases, Data models, Scope boundaries, Backward compatibility.
- Record architectural decisions in Architecture Decision Records (`.agents/adr/`).

### Step 2: Spec-Driven Development (`/to-spec`)
- Every feature must have clear specification documents or Type Interfaces/Schemas before writing code:
  - Request/Response Models (Pydantic / Type contracts).
  - Error Codes & Exceptions.
  - State Transitions & Invariants.

### Step 3: Test-Driven Development (`/tdd`, `/implement`)
- **Red**: Write Unit Tests / Integration Tests first. Run the test suite and verify tests **FAIL**.
- **Green**: Write the minimal, cleanest code required to make tests **PASS**.
- **Refactor**: Optimize code, eliminate duplication, and ensure adherence to Clean Architecture.
- **No tests = Incomplete work**.

### Step 4: Task Checklist & Live Tracking
- All tasks must be tracked in a checklist (`[ ]`, `[x]`).
- Update checklists **simultaneously** as each sub-task is completed, never batch updates at the end.

---

## 3. Clean Architecture & Code Standards

The Minder codebase strictly adheres to an independent 4-tier architecture:

1. **Domain Layer (`src/minder/domain/`)**:
   - Pure domain entities (`Workspace`, `Repository`, `Memory`, `Skill`, `Session`, `Contract`, `CodeChunk`).
   - Strictly NO imports of infrastructure libraries (FastAPI, SQLite, Turbovec, llama-cpp, LangGraph).
2. **Application Layer (`src/minder/application/`)**:
   - Use cases, DTOs, and Interfaces/Ports (`IVectorStore`, `IOperationalStore`, `IEmbeddingProvider`, `ILLMProvider`).
   - Business orchestration logic.
3. **Infrastructure Layer (`src/minder/infrastructure/`, `src/minder/store/`, `src/minder/llm/`)**:
   - SQLite WAL repositories, Turbovec ANN index, Qwen3.5 2B engine / Detached OpenAI client adapter.
   - All heavy I/O operations must run non-blocking via async or thread offloading.
4. **Presentation Layer (`src/minder/presentation/`, `src/minder/transport/`)**:
   - Fast MCP Endpoints (SSE/Stdio), Admin REST API, CLI commands.
   - **Golden Rule**: MCP Tool endpoints must be **Lean & Deterministic (< 50ms)**. FORBIDDEN to nest LLM reasoning loops inside retrieval tools.

---

## 4. Ubiquitous Language

Refer to `CONTEXT.md` for standardized terminology across the entire codebase:
- **Workspace**: A collection of Git Repositories belonging to the same project/solution.
- **Contract**: Standardized specification of API Routes, DTOs, Protobuf/gRPC schemas, or Event messages across services.
- **Lean Tool**: MCP tool that returns structured data or code snippets directly, without internal LLM loops.
- **Team Hub**: Centralized server storing shared Knowledge Graphs, Vector Indices, and Shared Memories of a Workspace.
