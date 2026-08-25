# 01. System Overview — System Architecture Topology

Minder is an Engineering Intelligence Platform built for AI Coding Agents adhering to the Model Context Protocol (MCP) standards.

---

## 1. Hub & Spoke Topology (Workspace-Centric)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SHARED MINDER TEAM HUB                         │
│               (Central Server / Cloud VM / Docker Container)            │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ WORKSPACE (e.g., "FinTech Platform")                              │  │
│  │  - Repositories: [backend-api, frontend-web, auth-service, etc.]  │  │
│  │  - Cross-Repo Contract Registry (Routes, DTOs, gRPC, MQ Events)   │  │
│  │  - Unified Vector Store (Turbovec ANN Index)                      │  │
│  │  - Shared Team Memories & Architectural Decisions                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Fast MCP SSE / Stdio / REST API)
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ Dev A (Laptop)   │       │ Dev A (Office PC)│       │ Dev B (Remote)   │
│ - Cursor / Claude│       │ - VS Code / MCP  │       │ - Windsurf / MCP │
│ - Auto Git Watch │       │ - Auto Git Watch │       │ - Auto Git Watch │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

---

## 2. Four-Tier Clean Architecture

The system is decoupled into four distinct tiers:

1. **Domain Layer (`src/minder/domain/`)**:
   - Pure domain entities: `Workspace`, `Repository`, `Contract`, `CodeChunk`, `Memory`, `Skill`, `SessionState`.
   - Zero external framework or infrastructure dependencies.

2. **Application Layer (`src/minder/application/`)**:
   - Use Cases, DTOs, and Interfaces (Ports): `IOperationalStore`, `IVectorStore`, `IGraphRepository`, `IEmbeddingProvider`, `ILLMProvider`.
   - Orchestrates code search, contract queries, AST extraction, and session continuity.

3. **Infrastructure Layer (`src/minder/infrastructure/`)**:
   - Technical implementations: SQLite (WAL mode), Turbovec ANN, AST Multi-language Code Splitter, Qwen3.5 2B engine, Detached OpenAI-compatible HTTP client adapter.

4. **Presentation Layer (`src/minder/presentation/`)**:
   - Fast MCP Endpoints (SSE / Stdio), Admin REST API, CLI Daemon (`minder connect`, `minder sync`, `minder watch`).
   - Every MCP retrieval endpoint is **Lean & Deterministic (< 50ms)**.
