# Minder — Task Breakdown

> **Document version**: 1.0 — 2026-04-01
> **Status**: READY FOR REVIEW

---

## Team Structure (4 Members)

| Role | ID | Responsibilities |
|---|---|---|
| **Backend Lead** | `BE` | Auth, data models, stores, MCP tools, workflow engine, API design |
| **Platform Engineer** | `PE` | Project setup, config, transport layer, Docker, CI/CD, database migrations |
| **ML/RAG Engineer** | `ML` | Embedding, LLM integration, LangGraph pipeline, retrieval, reranking, learning |
| **Frontend/DevOps Engineer** | `FE` | Dashboard (backend + frontend), observability, monitoring, load testing |

---

## Phase 1 — Foundation: MCP Server, Auth, Search, CI/CD

**Goal**: Deliver a working SSE-first MCP server with auth, repo-local state, basic search, and CI/CD.

### Current Implementation Audit

> **Current status as of 2026-04-03**: `IN PROGRESS`
>
> Phase 1 is **not closed yet**. The repository currently has the data/config/auth foundation and a usable local query pipeline, but several original Phase 1 deliverables are still missing or only partially implemented, especially:
> - MCP transport layer (`SSE`, `stdio`)
> - repo-local `.minder/` state store
> - standalone workflow/memory/auth/session MCP tool surface
> - deployment automation (`docker/Dockerfile`, `docker-compose.dev.yml`)
> - CI/CD and release workflows under `.github/workflows/`
> - bootstrap scripts such as `seed_skills.py`, `download_models.sh`, `create_admin.py`
>
> The codebase should currently be read as:
> - **Implemented foundation**: config, models, relational store, auth service/RBAC, embedding providers, vector/document/history/error stores, graph pipeline, query/search/ingest tools, Docker sandbox contract.
> - **Runnable local flow today**: ingest repo -> run `minder_query` / `minder_search_code` / `minder_search_errors` -> optional workflow-aware reasoning -> verification contract -> history/error persistence.
> - **Not yet runnable as originally specified for Phase 1**: authenticated MCP server over SSE/stdio with deployment stack and CI/release automation.

### Phase 1 Progress Tracker

Use this table as the working control board for Phase 1. Update `Status`, `Wave`, `Blocker`, and `Last update` after every implementation wave.

| Task | Owner | Wave | Status | Blocker | Last update |
|---|---|---|---|---|---|
| `P1-T01` Project Initialization | `PE` | `done` | `DONE` | `-` | `Python 3.14 baseline verified` |
| `P1-T02` Configuration System | `PE` | `done` | `DONE` | `-` | `Config tests passing` |
| `P1-T03` Data Models | `BE` | `done` | `DONE` | `-` | `Model coverage in place` |
| `P1-T04` Relational Store (SQLite) | `BE` | `done` | `DONE` | `-` | `CRUD and tests in place` |
| `P1-T05` Auth Layer | `BE` | `done` | `DONE` | `-` | `JWT/RBAC/API key flow implemented` |
| `P1-T06` SSE Transport | `1` | `PARTIAL` | `Actual SSE server lifecycle/network listener still missing` | `Wave 1 transport facade + tests committed` |
| `P1-T07` Stdio Transport | `1` | `PARTIAL` | `Real stdio server lifecycle still missing` | `Wave 1 transport facade + tests committed` |
| `P1-T08` Auth Middleware for SSE | `1` | `PARTIAL` | `Not yet bound to real SSE connection/session lifecycle` | `Dispatch-path auth integration completed` |
| `P1-T09` Embedding Layer (Qwen GGUF) | `backlog` | `PARTIAL` | `Model provisioning/runtime environment not closed` | `Optional llama_cpp path exists` |
| `P1-T10` Embedding Fallback (OpenAI) | `done` | `DONE` | `-` | `Fallback provider exists` |
| `P1-T11` Vector Store (Milvus Lite) | `backlog` | `PARTIAL` | `Real Milvus Lite deployment path not packaged` | `Vector substrate exists` |
| `P1-T12` Repository-Local State Management | `2` | `DONE` | `-` | `Wave 2 repo-state store + integration test completed` |
| `P1-T13` Workflow Engine (Basic) | `2` | `PARTIAL` | `Final MCP transport registration still missing` | `Workflow tool module + repo-state persistence completed` |
| `P1-T14` Memory & Search Tools (Basic) | `2` | `DONE` | `-` | `Memory/search modules + integration test completed` |
| `P1-T15` Auth MCP Tools | `2` | `PARTIAL` | `Final MCP transport registration still missing` | `Auth tool module contract completed` |
| `P1-T16` Session Tools | `2` | `PARTIAL` | `Final MCP transport registration still missing` | `Session tool module contract completed` |
| `P1-T17` Skill Seeding | `3` | `NOT STARTED` | `Script missing` | `Planned after tool surface` |
| `P1-T18` Model Download Script | `3` | `NOT STARTED` | `Script missing` | `Planned after tool surface` |
| `P1-T19` Docker Development Stack | `3` | `PARTIAL` | `docker/Dockerfile and docker-compose.dev.yml missing` | `Sandbox image only` |
| `P1-T20` GitHub Actions CI | `3` | `NOT STARTED` | `.github/workflows/ci.yml missing` | `Planned with deployment assets` |
| `P1-T21` GitHub Actions Release | `3` | `NOT STARTED` | `.github/workflows/release.yml missing` | `Planned with deployment assets` |
| `P1-T22` Admin Creation Script | `3` | `NOT STARTED` | `Script missing` | `Planned with bootstrap scripts` |
| `P1-VERIFY` Phase 1 Acceptance Test | `4` | `NOT STARTED` | `Depends on Waves 1-3` | `Gate added after implementation` |

### Phase 1 Status Map

| Task | Status | Notes |
|---|---|---|
| `P1-T01` Project Initialization | `DONE` | `uv`, `ruff`, `mypy`, `pytest`, project layout, Python 3.14 baseline are in place. |
| `P1-T02` Configuration System | `DONE` | [`src/minder/config.py`](/Users/trungtran/ai-agents/minder/src/minder/config.py) exists with tested settings sections. |
| `P1-T03` Data Models | `DONE` | Core SQLAlchemy/Pydantic models are present under [`src/minder/models/`](/Users/trungtran/ai-agents/minder/src/minder/models). |
| `P1-T04` Relational Store (SQLite) | `DONE` | Async relational store exists in [`src/minder/store/relational.py`](/Users/trungtran/ai-agents/minder/src/minder/store/relational.py). |
| `P1-T05` Auth Layer | `DONE` | Auth service, JWT helpers, API key hashing, and RBAC are implemented under [`src/minder/auth/`](/Users/trungtran/ai-agents/minder/src/minder/auth). |
| `P1-T06` SSE Transport | `PARTIAL` | [`src/minder/transport/sse.py`](/Users/trungtran/ai-agents/minder/src/minder/transport/sse.py) now exists with transport facade, tool registration, dispatch, and integration tests; network listener wiring is still pending. |
| `P1-T07` Stdio Transport | `PARTIAL` | [`src/minder/transport/stdio.py`](/Users/trungtran/ai-agents/minder/src/minder/transport/stdio.py) now exists with the same dispatch contract as SSE; real stdio server lifecycle wiring is still pending. |
| `P1-T08` Auth Middleware for SSE | `PARTIAL` | [`src/minder/auth/middleware.py`](/Users/trungtran/ai-agents/minder/src/minder/auth/middleware.py) is now integrated into the transport dispatch path and covered by transport tests, but not yet bound to an actual SSE server connection lifecycle. |
| `P1-T09` Embedding Layer (Qwen GGUF) | `PARTIAL` | Interface and optional `llama_cpp` runtime path exist; production model provisioning is not bundled yet. |
| `P1-T10` Embedding Fallback (OpenAI) | `DONE` | OpenAI fallback provider exists in [`src/minder/embedding/openai.py`](/Users/trungtran/ai-agents/minder/src/minder/embedding/openai.py). |
| `P1-T11` Vector Store (Milvus Lite) | `PARTIAL` | Vector search substrate exists in [`src/minder/store/vector.py`](/Users/trungtran/ai-agents/minder/src/minder/store/vector.py), but repo does not yet ship a real Milvus Lite deployment path. |
| `P1-T12` Repository-Local State Management | `DONE` | [`src/minder/store/repo_state.py`](/Users/trungtran/ai-agents/minder/src/minder/store/repo_state.py) now persists `.minder/workflow.json`, `context.json`, `relationships.json`, and `artifacts/` with round-trip integration coverage. |
| `P1-T13` Workflow Engine (Basic) | `PARTIAL` | [`src/minder/tools/workflow.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/workflow.py) now provides workflow get/step/update/guard with DB + repo-state persistence, but full MCP transport exposure is still pending. |
| `P1-T14` Memory & Search Tools (Basic) | `DONE` | [`src/minder/tools/memory.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/memory.py) and [`src/minder/tools/search.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/search.py) now exist with semantic recall/list/delete flow and integration coverage. |
| `P1-T15` Auth MCP Tools | `PARTIAL` | [`src/minder/tools/auth.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/auth.py) now provides login/whoami/manage module contracts, but transport registration as MCP tools is still pending. |
| `P1-T16` Session Tools | `PARTIAL` | [`src/minder/tools/session.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/session.py) now provides create/save/restore/context module contracts, but transport registration as MCP tools is still pending. |
| `P1-T17` Skill Seeding | `NOT STARTED` | `scripts/seed_skills.py` does not exist yet. |
| `P1-T18` Model Download Script | `NOT STARTED` | `scripts/download_models.sh` does not exist yet. |
| `P1-T19` Docker Development Stack | `PARTIAL` | [`docker/Dockerfile.sandbox`](/Users/trungtran/ai-agents/minder/docker/Dockerfile.sandbox) exists for verification, but `docker/Dockerfile` and `docker/docker-compose.dev.yml` are missing. |
| `P1-T20` GitHub Actions CI | `NOT STARTED` | `.github/workflows/ci.yml` does not exist yet. |
| `P1-T21` GitHub Actions Release | `NOT STARTED` | `.github/workflows/release.yml` does not exist yet. |
| `P1-T22` Admin Creation Script | `NOT STARTED` | `scripts/create_admin.py` does not exist yet. |
| `P1-VERIFY` Phase 1 Acceptance Test | `NOT STARTED` | `tests/integration/test_phase1_gate.py` does not exist yet. |

### Current Runnable Flow

The repository currently supports this **local development flow**, which is broader in some Phase 2 areas than the unfinished Phase 1 MCP/deployment surface:

1. Configure the project with [`src/minder/config.py`](/Users/trungtran/ai-agents/minder/src/minder/config.py) and `uv`.
2. Ingest repository files through [`src/minder/tools/ingest.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/ingest.py).
3. Query the agentic pipeline through [`src/minder/tools/query.py`](/Users/trungtran/ai-agents/minder/src/minder/tools/query.py).
4. Retrieve semantic code/error/document context from the vector/document/history stores.
5. Apply workflow-aware planning and reasoning through the graph nodes under [`src/minder/graph/`](/Users/trungtran/ai-agents/minder/src/minder/graph).
6. Run verification through subprocess or Docker contract in [`src/minder/graph/nodes/verification.py`](/Users/trungtran/ai-agents/minder/src/minder/graph/nodes/verification.py).
7. Inspect and smoke-test the end-to-end local flow using [`scripts/phase2_manual_smoke.py`](/Users/trungtran/ai-agents/minder/scripts/phase2_manual_smoke.py).

### Phase 1 Closure Work Still Needed

Before Phase 1 can be considered closed against the original spec, the remaining work is:

1. Build real MCP transports for `SSE` and `stdio`.
2. Expose workflow, memory, auth, and session MCP tools as standalone tool modules.
3. Add repo-local `.minder/` state persistence.
4. Add bootstrap scripts for admin creation, skill seeding, and model download.
5. Add development deployment assets: `docker/Dockerfile` and `docker/docker-compose.dev.yml`.
6. Add CI and release workflows under `.github/workflows/`.
7. Add and pass `tests/integration/test_phase1_gate.py`.

### Tasks

#### P1-T01: Project Initialization
- **Owner**: `PE`
- **Requirement**: Initialize Python 3.14+ project with `uv`, configure `ruff` (lint + format), `mypy` (type check), `pytest`. Create `pyproject.toml`, directory structure per `06-operations-and-delivery.md`.
- **Result**: Running `uv sync`, `ruff check .`, `mypy src/`, and `pytest` all pass on an empty project. Directory structure matches spec.

#### P1-T02: Configuration System
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/config.py` using Pydantic Settings. Load from `minder.toml` and env vars. Cover all config sections (server, auth, embedding, llm, vector_store, relational_store, retrieval, cache, verification, workflow, seeding).
- **Result**: Config loads from TOML file, env overrides work, missing required fields raise `ValidationError`. Unit tests pass for all sections.

#### P1-T03: Data Models
- **Owner**: `BE`
- **Requirement**: Implement all Pydantic/SQLAlchemy models in `src/minder/models/` — User, Skill, Session, Workflow, Repository, RepositoryWorkflowState, History, Error, Document, Rule, Feedback, Metadata. Follow schemas from `03-data-model-and-tools.md`.
- **Result**: All models instantiate correctly, fields match spec, serialization/deserialization works. Unit tests validate all field types and constraints.

#### P1-T04: Relational Store (SQLite)
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/store/relational.py` with SQLite backend. CRUD operations for User, Session, Workflow, Repository, and RepositoryWorkflowState. Use async SQLAlchemy.
- **Result**: All CRUD operations work. Data persists across restarts. Unit tests cover create, read, update, delete, and query by filters.

#### P1-T05: Auth Layer — User, API Keys, JWT, RBAC
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/auth/` — user registration, API key generation with `mk_` prefix, bcrypt hashing, JWT issuance/validation with PyJWT, role-based access (admin, member, readonly).
- **Result**: Users register, login with API key, receive JWT. JWT contains user_id, email, role. RBAC decorator blocks unauthorized access. Unit tests cover all auth flows and edge cases.

#### P1-T06: SSE Transport
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/transport/sse.py` — SSE-based MCP transport as primary. Use official Python `mcp` SDK. Server listens on configured host:port.
- **Result**: MCP client connects via SSE, sends tool calls, receives responses. Connection persists for session duration. Integration test validates round-trip.

#### P1-T07: Stdio Transport
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/transport/stdio.py` — stdio-based MCP transport for local dev. Same tool surface as SSE.
- **Result**: MCP client connects via stdio, tool calls work identically to SSE. Integration test validates round-trip.

#### P1-T08: Auth Middleware for SSE
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/auth/middleware.py` — JWT validation on SSE connections. Extract user identity, inject into request context. Reject unauthorized connections.
- **Result**: Unauthenticated SSE connections are rejected with 401. Valid JWT grants access with user context available to all tools. Integration test validates auth flow.

#### P1-T09: Embedding Layer (Qwen GGUF)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/embedding/qwen.py` — load `Qwen/Qwen3-Embedding-0.6B` GGUF via `llama-cpp-python`. Generate 1024-dim embeddings. Implement `src/minder/embedding/base.py` as abstract interface.
- **Result**: Text input → 1024-dim vector output. Model loads from configured path. Unit test validates embedding dimensions and determinism.

#### P1-T10: Embedding Fallback (OpenAI)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/embedding/openai.py` — OpenAI `text-embedding-3-small` as optional fallback. Same interface as Qwen embedder. Auto-fallback when local model fails and OpenAI key is configured.
- **Result**: When Qwen unavailable and API key set, OpenAI embeddings are used transparently. Unit test validates fallback logic.

#### P1-T11: Vector Store (Milvus Lite)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/store/vector.py` — Milvus Lite integration. Collections for skills, documents, errors. Insert, search by vector, delete. Score threshold filtering.
- **Result**: Vectors insert and search correctly. Top-K results return with scores. Threshold filtering works. Unit tests cover insert, search, delete, and filtering.

#### P1-T12: Repository-Local State Management
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/store/repo_state.py` — read/write `.minder/` directory in repositories. Manage `workflow.json`, `context.json`, `relationships.json`, `artifacts/` subdirectory.
- **Result**: State writes to `.minder/` directory. State reads back correctly. Missing directory is auto-created. Unit tests cover read, write, create, and restore.

#### P1-T13: Workflow Engine (Basic)
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/workflow.py` — `minder_workflow_get`, `minder_workflow_step`, `minder_workflow_update`, `minder_workflow_guard`. State machine tracks current step, completed steps, blockers, next step.
- **Result**: Workflow step advances correctly. Guard blocks invalid transitions. State persists to both server DB and repo-local `.minder/`. Unit tests cover full state machine.

#### P1-T14: Memory & Search Tools (Basic)
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/memory.py` and `src/minder/tools/search.py` — `minder_memory_store`, `minder_memory_recall`, `minder_memory_list`, `minder_memory_delete`, `minder_search`. Vector-based semantic search with embedding layer.
- **Result**: Store a skill → recall by semantic query → returns relevant result. List, delete work correctly. Integration test validates end-to-end search.

#### P1-T15: Auth MCP Tools
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/auth.py` — `minder_auth_login`, `minder_auth_whoami`, `minder_auth_manage`. Exposed as MCP tools through the SDK.
- **Result**: MCP client can call auth tools, receive JWT, check identity. Admin can manage users. Integration test validates MCP tool surface.

#### P1-T16: Session Tools
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/session.py` — `minder_session_create`, `minder_session_save`, `minder_session_restore`, `minder_session_context`.
- **Result**: Sessions create, save checkpoint, restore from checkpoint. Context includes repo, branch, open files. Unit tests cover lifecycle.

#### P1-T17: Skill Seeding
- **Owner**: `PE`
- **Requirement**: Implement `scripts/seed_skills.py` — clone external GitHub repo, parse skills from configured path, import into Milvus Lite with embeddings.
- **Result**: Skills from external repo are importable. Duplicates are handled. Script is idempotent. Integration test validates import.

#### P1-T18: Model Download Script
- **Owner**: `PE`
- **Requirement**: Implement `scripts/download_models.sh` — download Qwen embedding and LLM GGUF files to `~/.minder/models/`. Verify checksums. Skip if already present.
- **Result**: Models download successfully. Checksum validation passes. Re-run skips existing files.

#### P1-T19: Docker Development Stack
- **Owner**: `PE`
- **Requirement**: Create `docker/Dockerfile`, `docker/docker-compose.dev.yml`. Container runs Minder server with SSE transport. Volume mounts for dev. Include model download in build.
- **Result**: `docker compose -f docker/docker-compose.dev.yml up` starts Minder. MCP client connects via SSE to container.

#### P1-T20: GitHub Actions CI
- **Owner**: `PE`
- **Requirement**: Create `.github/workflows/ci.yml` — checkout, setup Python 3.14 + uv, install deps, ruff lint, mypy, unit tests, integration tests, coverage report, Docker build verification.
- **Result**: CI runs on PR and push to main. All steps pass. Coverage report generated.

#### P1-T21: GitHub Actions Release
- **Owner**: `PE`
- **Requirement**: Create `.github/workflows/release.yml` — triggered on version tags. Run full CI, build multi-arch Docker images, push to ghcr.io, build Python package, create GitHub Release.
- **Result**: Tagging `v0.1.0` triggers release. Docker image published. GitHub Release created with artifacts.

#### P1-T22: Admin Creation Script
- **Owner**: `PE`
- **Requirement**: Implement `scripts/create_admin.py` — create initial admin user with email from config. Generate and display API key. Idempotent.
- **Result**: Admin user created. API key displayed. Re-run skips if admin exists.

### Phase 1 Verification Gate

#### P1-VERIFY: Phase 1 Acceptance Test
- **Owner**: `BE` + `PE`
- **Requirement**: Write and run `tests/integration/test_phase1_gate.py` that validates **all** Phase 1 deliverables end-to-end:
  1. Server starts with SSE transport
  2. Admin user is created via script
  3. Client connects via SSE, authenticates, receives JWT
  4. Workflow tools report current step and next step
  5. Memory store → semantic search → recall works
  6. Repository-local `.minder/` state writes and restores
  7. CI pipeline passes on GitHub Actions
- **Result**: All 7 checks pass. Phase 1 is complete.

---

## Phase 2 — Agentic Pipeline: LangGraph and Guided Execution

**Goal**: Deliver end-to-end agentic pipeline with workflow-aware reasoning and Docker-based verification.

### Tasks

#### P2-T01: LangGraph State Definition
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/state.py` — define the LangGraph state schema. Fields: query, plan, retrieved_docs, reranked_docs, workflow_context, reasoning_output, llm_output, guard_result, verification_result, evaluation.
- **Result**: State object instantiates, serializes, and deserializes correctly. Unit tests validate all fields.

#### P2-T02: Workflow Planner Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/workflow_planner.py` — determines current phase, validates prerequisites, decides next step, generates step-specific guidance.
- **Result**: Given a repo with configured workflow, node outputs correct phase, blockers, and guidance. Unit tests cover all workflow steps.

#### P2-T03: Planning Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/planning.py` — classify intent (code gen, debug, search, explain, refactor), select knowledge layer, choose retrieval strategy, estimate complexity.
- **Result**: Given a query, node outputs classified intent and execution plan. Unit tests cover all intent types.

#### P2-T04: Retriever Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/retriever.py` — generate query embedding, search Milvus, de-duplicate, filter by score threshold.
- **Result**: Given a query, returns ranked candidates from vector store. Unit tests validate retrieval and filtering.

#### P2-T05: Reasoning Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/reasoning.py` — build final prompt with retrieved context, inject workflow rules and step constraints, enforce current process stage.
- **Result**: Prompt output includes retrieved context + workflow instructions. Unit tests validate prompt construction.

#### P2-T06: LLM Node (Qwen Local)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/llm/qwen.py` and `src/minder/graph/nodes/llm.py` — load `Qwen3.5-0.8B` GGUF via `llama-cpp-python`. Route prompts to local model by default. Stream output.
- **Result**: Prompt in → generated text out. Model loads from configured path. Streaming works. Unit test validates generation.

#### P2-T07: LLM Fallback (OpenAI via LiteLLM)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/llm/openai.py` — OpenAI fallback via LiteLLM. Same interface as local LLM. Auto-fallback when local model fails and API key configured.
- **Result**: Fallback triggers transparently. Unit test validates fallback logic.

#### P2-T08: Guard Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/guard.py` — content safety checks, hallucination checks against sources, syntax checks for code, secrets/PII scanning.
- **Result**: Unsafe content is flagged. Hallucinated references are caught. Secrets in code are detected. Unit tests cover all guard types.

#### P2-T09: Verification Node (Docker Sandbox)
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/graph/nodes/verification.py` and `docker/Dockerfile.sandbox` — Docker sandbox execution (no network, read-only root, resource limits). Run generated code, execute tests, compare results.
- **Result**: Generated code runs in isolated container. Test results captured. Timeout enforced. Integration test validates sandbox execution.

#### P2-T10: Verification Node (Dev Subprocess)
- **Owner**: `PE`
- **Requirement**: Add subprocess verification mode to verification node. Only available when `verification.sandbox = "subprocess"` (dev mode).
- **Result**: In dev mode, code runs in subprocess without Docker. Same interface, same result format. Unit test validates subprocess mode.

#### P2-T11: Evaluator Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/evaluator.py` — score quality and correctness, update metrics, store history and feedback, trigger learning signals.
- **Result**: Evaluation scores are calculated and stored. History records created. Unit tests validate scoring logic.

#### P2-T12: Graph Assembly
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/graph.py` and `src/minder/graph/edges.py` — assemble all nodes into LangGraph. Define edges and conditional routing (guard fail → retry, verification fail → reasoning loop).
- **Result**: Full graph executes end-to-end. Conditional edges route correctly. Integration test validates complete pipeline.

#### P2-T13: History and Error Stores
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/store/history.py` and `src/minder/store/error.py` — user-scoped history with reasoning traces, error store with resolution tracking and vector search.
- **Result**: History records per session per user. Errors store with embeddings for similarity search. Unit tests cover CRUD and scoping.

#### P2-T14: Query and Search Tools
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/query.py` — `minder_query` (full RAG pipeline), `minder_search_code`, `minder_search_errors`. Wire to LangGraph engine.
- **Result**: `minder_query` triggers full pipeline. Code search and error search work semantically. Integration test validates end-to-end.

#### P2-T15: Workflow-Aware Prompt Injection
- **Owner**: `ML` + `BE`
- **Requirement**: Workflow engine injects current-step instructions into every prompt. MCP response explicitly tells the LLM the next valid step.
- **Result**: When TDD workflow is active, prompts include "Current step: Test Writing. Write tests before implementation." Integration test validates injection.

### Phase 2 Verification Gate

#### P2-VERIFY: Phase 2 Acceptance Test
- **Owner**: `ML` + `BE`
- **Requirement**: Write and run `tests/integration/test_phase2_gate.py`:
  1. Full `minder_query` returns a reasoned response with sources
  2. TDD-configured repo causes prompt to enforce test-first
  3. Generated code executes in Docker sandbox
  4. Guard catches unsafe output
  5. Workflow state advances after step completion
  6. History and error stores record the session
- **Result**: All 6 checks pass. Phase 2 is complete.

---

## Phase 2.1 — Runtime Fidelity and Orchestration Replacement

**Goal**: Replace the current minimal internal pipeline with the real Phase 2 runtime stack while preserving the existing Phase 2 tool surface.

### Tasks

#### P2.1-T01: LangGraph Runtime Replacement
- **Owner**: `ML`
- **Requirement**: Replace the current internal graph executor with real `LangGraph` orchestration in `src/minder/graph/graph.py` and `src/minder/graph/edges.py`. Preserve the current state contract and node boundaries.
- **Result**: Execution uses LangGraph state transitions and conditional edges instead of a hand-rolled linear runner.

#### P2.1-T02: State Contract Normalization
- **Owner**: `ML`
- **Requirement**: Normalize `src/minder/graph/state.py` so the state shape fully matches the documented Phase 2 contract and supports retry metadata, source attribution, and workflow transition reasons.
- **Result**: State is stable enough for retry loops, verification feedback, and Phase 3 retrieval extensions.

#### P2.1-T03: Local LLM Runtime via llama-cpp-python
- **Owner**: `ML`
- **Requirement**: Replace the placeholder local LLM in `src/minder/llm/qwen.py` with real `llama-cpp-python` loading of `Qwen3.5-0.8B` GGUF, including streaming support and structured generation result.
- **Result**: Local inference runs against the configured GGUF model path and streams usable output.

#### P2.1-T04: OpenAI Fallback via LiteLLM
- **Owner**: `ML`
- **Requirement**: Replace the placeholder fallback in `src/minder/llm/openai.py` with real LiteLLM-backed OpenAI fallback. Trigger only when local generation fails and API key is configured.
- **Result**: Fallback behavior is transparent, configurable, and testable.

#### P2.1-T05: LLM Node Error and Fallback Policy
- **Owner**: `ML`
- **Requirement**: Update `src/minder/graph/nodes/llm.py` to distinguish retryable local runtime failure, terminal local failure, and fallback-eligible failure. Persist provider/model metadata into output.
- **Result**: The graph can reliably decide whether to retry, fallback, or fail.

#### P2.1-T06: Conditional Graph Routing
- **Owner**: `ML`
- **Requirement**: Implement real conditional routing for `guard fail -> retry/stop`, `verification fail -> reasoning loop`, and `llm local fail -> fallback`.
- **Result**: The graph behavior matches the original Phase 2 architecture instead of always doing a single pass.

#### P2.1-T07: Phase 2.1 Runtime Tests
- **Owner**: `ML`
- **Requirement**: Add focused unit/integration coverage for LangGraph execution, local LLM loading contract, streaming behavior, and fallback path selection.
- **Result**: Runtime replacement is covered before moving to verification and retrieval closure.

---

## Phase 2.2 — Verification, Retrieval, and Workflow Closure

**Goal**: Close the remaining Phase 2 gaps in retrieval, Docker verification, and workflow enforcement so Phase 3 can assume a real agentic foundation.

### Tasks

#### P2.2-T01: Retriever Node on Embedding + Vector Search
- **Owner**: `ML`
- **Requirement**: Replace lexical repository scan in `src/minder/graph/nodes/retriever.py` with embedding-driven retrieval using the existing embedding/vector store stack from Phase 1. Search Milvus-backed documents/errors, de-duplicate, and apply score threshold.
- **Result**: Phase 2 retrieval is semantic and aligns with the original spec.

#### P2.2-T02: Code Search Tool Alignment
- **Owner**: `BE`
- **Requirement**: Update `src/minder/tools/query.py` so `minder_search_code` uses the same retrieval substrate as `minder_query`, not a separate file-walk fallback except as explicit dev fallback.
- **Result**: Search behavior is consistent across tools.

#### P2.2-T03: Real Docker Sandbox Verification
- **Owner**: `PE`
- **Requirement**: Replace the Docker stub in `src/minder/graph/nodes/verification.py` with actual container execution using `docker/Dockerfile.sandbox`, no-network mode, read-only root, timeout, and captured stdout/stderr.
- **Result**: Generated code is executed in a real isolated sandbox.

#### P2.2-T04: Dev Subprocess Verification Contract
- **Owner**: `PE`
- **Requirement**: Keep subprocess mode only for dev, but align its result schema and error handling exactly with Docker mode.
- **Result**: Both verification modes return the same contract and differ only by runtime backend.

#### P2.2-T05: Workflow Instruction Injection Hardening
- **Owner**: `BE` + `ML`
- **Requirement**: Strengthen prompt injection so every generation request carries active workflow, current step, blockers, next valid step, and artifact expectations from repository workflow state.
- **Result**: The LLM is explicitly constrained by workflow state on every call.

#### P2.2-T06: Workflow State Transition Policy
- **Owner**: `BE`
- **Requirement**: Make workflow advancement policy explicit: only advance on guard pass plus successful verification when verification is required; persist transition reason and keep failed states non-advancing.
- **Result**: Step movement is deterministic and auditable.

#### P2.2-T07: MCP Surface Completion for Phase 2
- **Owner**: `BE`
- **Requirement**: Ensure `minder_query`, `minder_search_code`, and `minder_search_errors` expose provider, sources, workflow instruction summary, and verification status in a stable response contract.
- **Result**: Tool outputs are stable enough for clients and Phase 3 resource/prompt layering.

#### P2.2-T08: History and Error Recording Hardening
- **Owner**: `BE`
- **Requirement**: Expand history/error persistence so retries, fallback provider choice, guard failures, and verification failures are recorded with enough context for later retrieval.
- **Result**: Phase 3 can build on trustworthy session and failure history.

### Phase 2.x Verification Gate

#### P2.X-VERIFY: Runtime Fidelity Gate Before Phase 3
- **Owner**: `ML` + `BE` + `PE`
- **Requirement**: Write and run `tests/integration/test_phase2x_gate.py`:
  1. `minder_query` runs on the Phase 2.x orchestrator with conditional routing metadata
  2. Local Qwen runtime exposes runtime/provider metadata and stream chunks
  3. Local failure triggers fallback path when configured
  4. Search tools expose the same retrieval and source contract as query
  5. Generated Python executes through a real or injectable Docker runner contract
  6. Guard failure does not advance workflow state
  7. Verification failure records retry/transition state without false advancement
  8. History and error stores record retries, fallback, and failures
- **Result**: All 8 checks pass. Phase 2 is ready for Phase 3.

---

## Phase 3 — Advanced Retrieval, Knowledge Graph, Process Intelligence

**Goal**: Improve retrieval quality and add relationship-aware repository intelligence.

### Tasks

#### P3-T01: Reranking (Cross-Encoder)
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/reranker.py` — cross-encoder reranking with `sentence-transformers`, diversity filtering with MMR, recency weighting.
- **Result**: Reranked results are more relevant than raw vector search. Unit tests compare MRR before/after reranking.

#### P3-T02: BM25 Hybrid Retrieval
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/retrieval/hybrid.py` — combine vector search with BM25 keyword search. Configurable alpha weighting.
- **Result**: Hybrid search improves recall for keyword-heavy queries. Unit tests validate alpha blending.

#### P3-T03: Multi-Hop Retrieval
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/retrieval/multi_hop.py` — iterative retrieval that uses first-hop results to refine the query for second-hop.
- **Result**: Multi-hop returns results unreachable by single-hop. Unit tests validate iterative refinement.

#### P3-T04: MMR Diversity Filtering
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/retrieval/mmr.py` — Maximal Marginal Relevance to reduce redundancy in results.
- **Result**: Top-N results are diverse, not repetitive. Unit tests validate diversity scoring.

#### P3-T05: Knowledge Graph Store
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/store/graph.py` — store entities and relationships (modules, services, ownership, dependencies). Query by entity, by relationship type, by path.
- **Result**: Nodes and edges store and query correctly. Graph traversal works. Unit tests cover CRUD and traversal.

#### P3-T06: Document, Rule, Feedback Stores
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/store/document.py`, `src/minder/store/rule.py`, `src/minder/store/feedback.py` — full CRUD per schema in `03-data-model-and-tools.md`.
- **Result**: All three stores work with CRUD. Documents chunk and embed. Rules filter by scope. Feedback links to entities. Unit tests cover all operations.

#### P3-T07: AST-Aware Code Chunking
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/chunking/code_splitter.py` — parse code into AST, chunk by function/class boundaries. Preserve import context. Support Python, TypeScript, Java.
- **Result**: Code chunks align with function/class boundaries. Imports are preserved. Unit tests validate for each supported language.

#### P3-T08: Text Chunking
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/chunking/splitter.py` — LangChain text splitters for markdown, prose, and config files. Configurable chunk size and overlap.
- **Result**: Documents chunk with configurable size. Overlap preserves context. Unit tests validate chunking.

#### P3-T09: Ingestion Tools
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/tools/ingest.py` — `minder_ingest_file`, `minder_ingest_directory`, `minder_ingest_url`, `minder_ingest_git`, `minder_seed_skills`. Chunk → embed → store pipeline.
- **Result**: Files, directories, URLs, and git repos ingest end-to-end. Duplicates handled. Integration test validates ingestion pipeline.

#### P3-T10: Repository Relationship Tracking
- **Owner**: `BE`
- **Requirement**: Scan repositories for module structure, service dependencies, ownership info. Store in knowledge graph. Update on re-scan.
- **Result**: Repo scan produces graph of modules and dependencies. Re-scan updates graph. Unit tests validate scan and graph output.

#### P3-T11: MCP Resources and Prompts
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/resources/` (skills, repos, stats) and `src/minder/prompts/` (debug, review, explain, tdd_step). Expose as MCP resources and prompts.
- **Result**: MCP client can read resources and use prompt templates. Integration test validates resource and prompt access.

#### P3-T12: Workflow Intelligence Enhancement
- **Owner**: `BE` + `ML`
- **Requirement**: Workflow engine uses repo relationships and artifact lineage to provide richer guidance. Example: "Module X depends on Y, which has failing tests."
- **Result**: Workflow guidance includes dependency-aware context. Integration test validates enriched guidance.

### Phase 3 Verification Gate

#### P3-VERIFY: Phase 3 Acceptance Test
- **Owner**: `ML` + `BE`
- **Requirement**: Write and run `tests/integration/test_phase3_gate.py`:
  1. Multi-hop query across code + docs returns relevant cross-references
  2. Hybrid search improves MRR@10 over pure vector search
  3. Knowledge graph stores and queries repo relationships
  4. Ingestion pipeline processes a real repository
  5. MCP resources and prompts are accessible
  6. Workflow guidance includes dependency-aware context
- **Result**: All 6 checks pass. Phase 3 is complete.

---

## Phase 4 — Production Scale, Multi-User, Dashboard

**Goal**: Production-ready for teams with a dashboard for workflow administration.

### Tasks

#### P4-T01: PostgreSQL Migration
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/migration/alembic/` — migrate from SQLite to PostgreSQL. Alembic migrations for all tables. Config switch between SQLite (dev) and PostgreSQL (prod).
- **Result**: All data operations work on PostgreSQL. Migrations run forward and backward. Integration tests pass on both backends.

#### P4-T02: Milvus Standalone Migration
- **Owner**: `PE`
- **Requirement**: Update `src/minder/store/vector.py` — support Milvus Standalone alongside Milvus Lite. Config switch. Data migration script.
- **Result**: Vector operations work on Milvus Standalone. Performance improved for concurrent access. Integration tests pass.

#### P4-T03: Redis Cache Layer
- **Owner**: `PE`
- **Requirement**: Implement `src/minder/cache/redis.py` — Redis caching for embeddings, search results, and session data. TTL-based expiry. Configurable via `cache.provider = "redis"`.
- **Result**: Cache hit avoids re-computation. TTL expiry works. LRU fallback when Redis unavailable. Unit tests cover cache logic.

#### P4-T04: Rate Limiting and Quotas
- **Owner**: `BE`
- **Requirement**: Implement `src/minder/auth/rate_limiter.py` — per-user rate limiting on MCP tool calls. Configurable limits by role. Quota tracking.
- **Result**: Exceeding rate limit returns 429. Admin has higher limits. Quota is tracked. Unit tests cover rate limiting.

#### P4-T05: Observability Stack
- **Owner**: `FE`
- **Requirement**: Implement `src/minder/observability/` — OpenTelemetry tracing, Prometheus metrics, structured JSON logging, audit trails for auth and workflow events.
- **Result**: Traces flow through pipeline. Metrics exposed at `/metrics`. Audit log records all auth and workflow events. Integration test validates tracing.

#### P4-T06: Production Docker Compose
- **Owner**: `PE`
- **Requirement**: Create `docker/docker-compose.prod.yml` — Minder server, PostgreSQL, Milvus Standalone, Redis. Health checks, restart policies, volume management.
- **Result**: `docker compose -f docker/docker-compose.prod.yml up` starts full production stack. Health checks pass.

#### P4-T07: Dashboard Backend API
- **Owner**: `FE`
- **Requirement**: Implement `dashboard/backend/` — FastAPI app with endpoints for workflow CRUD, repo policies, user management, metrics, audit logs, CI/CD status. Auth via Minder JWT.
- **Result**: All CRUD endpoints work. Auth enforces admin role. Integration tests validate all endpoints.

#### P4-T08: Dashboard Frontend — Workflow Management
- **Owner**: `FE`
- **Requirement**: Build `dashboard/frontend/` — Next.js app. Pages: workflow list, workflow editor (step order, gate config), workflow assignment to repos.
- **Result**: Admin creates/edits workflows in UI. Workflows assign to repos. UI validates step order.

#### P4-T09: Dashboard Frontend — Repository & User Management
- **Owner**: `FE`
- **Requirement**: Pages: repo list with workflow state and progress, user management (CRUD, API key rotation, role assignment), blocked items view.
- **Result**: Admin sees repo progress, manages users, views blocked items. All CRUD operations work through UI.

#### P4-T10: Dashboard Frontend — Observability
- **Owner**: `FE`
- **Requirement**: Pages: metrics dashboard (latency, success rates, usage), audit log viewer, CI/CD status integration.
- **Result**: Metrics display in charts. Audit log is searchable. CI/CD status shows per repo.

#### P4-T11: Load Testing
- **Owner**: `PE`
- **Requirement**: Write load tests with `locust` or `k6` — simulate 50 concurrent users making MCP tool calls. Measure p95 latency, error rate, memory usage.
- **Result**: System handles 50 concurrent users. p95 latency < 5s for queries. Error rate < 1%. Memory < 4GB.

#### P4-T12: Security Review
- **Owner**: `BE` + `PE`
- **Requirement**: Review auth (JWT validation, API key storage, RBAC enforcement), isolation (user data scoping, sandbox escapes), input validation, and dependency vulnerabilities.
- **Result**: Security review report with findings and remediations. No critical vulnerabilities. All findings addressed.

### Phase 4 Verification Gate

#### P4-VERIFY: Phase 4 Acceptance Test
- **Owner**: `FE` + `PE`
- **Requirement**: Write and run `tests/e2e/test_phase4_gate.py` + manual dashboard verification:
  1. Admin configures a workflow in the dashboard
  2. Workflow is assigned to a repo and state is visible
  3. 50 concurrent users operate without errors
  4. Metrics, audit logs, and tracing work end-to-end
  5. PostgreSQL and Milvus Standalone handle production load
  6. Security review passes with no critical findings
- **Result**: All 6 checks pass. Phase 4 is complete.

---

## Phase 5 — Learning and Self-Improvement

**Goal**: Let Minder learn from workflows, failures, and feedback to improve over time.

### Tasks

#### P5-T01: Pattern Extractor
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/learning/pattern_extractor.py` — analyze successful workflow sessions, extract reusable code patterns and decision sequences.
- **Result**: Patterns are extracted from completed workflows. Patterns store as skills with embeddings. Unit tests validate extraction.

#### P5-T02: Skill Synthesizer
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/learning/skill_synthesizer.py` — generate new skills from successful sessions. Merge similar skills. Quality-score new skills.
- **Result**: New skills auto-generate from sessions. Duplicates merged. Quality scores calculated. Unit tests validate synthesis.

#### P5-T03: Error Learner
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/learning/error_learner.py` — when an error is resolved, store the resolution. Link similar future errors to known resolutions.
- **Result**: Resolved errors surface as suggestions for similar future errors. Unit tests validate linking.

#### P5-T04: Quality Optimizer
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/learning/quality_optimizer.py` — tune retrieval parameters (top_k, threshold, alpha) based on feedback data. A/B test retrieval strategies.
- **Result**: Retrieval parameters auto-tune based on feedback. A/B tests run and report results. Unit tests validate optimization logic.

#### P5-T05: Reflection Node
- **Owner**: `ML`
- **Requirement**: Implement `src/minder/graph/nodes/reflection.py` — post-run self-evaluation. Analyze what worked, what didn't, and store insights for future sessions.
- **Result**: Reflection generates actionable insights after each pipeline run. Insights stored and retrievable. Unit tests validate reflection.

#### P5-T06: Memory Compaction
- **Owner**: `BE`
- **Requirement**: Enhance `minder_memory_compact` — merge stale entries, re-embed with latest model, prune low-quality entries below threshold.
- **Result**: Compaction reduces storage, re-vectors stale entries, prunes junk. Unit tests validate compaction.

### Phase 5 Verification Gate

#### P5-VERIFY: Phase 5 Acceptance Test
- **Owner**: `ML` + `BE`
- **Requirement**: Write and run `tests/integration/test_phase5_gate.py`:
  1. Pattern extractor produces skills from workflow history
  2. Skill synthesizer generates and deduplicates new skills
  3. Error learner suggests resolutions for similar errors
  4. Quality optimizer improves MRR@10 after feedback cycles
  5. Reflection node produces insights after a pipeline run
  6. Memory compaction reduces storage without losing quality
- **Result**: All 6 checks pass. Phase 5 is complete.

---

## Summary

| Phase | Tasks | Verification | Key Deliverable |
|---|---|---|---|
| **Phase 1** | 22 tasks | P1-VERIFY | Working MCP server with auth, search, workflow, CI/CD |
| **Phase 2** | 15 tasks | P2-VERIFY | Full LangGraph agentic pipeline with verification |
| **Phase 3** | 12 tasks | P3-VERIFY | Advanced retrieval, knowledge graph, ingestion |
| **Phase 4** | 12 tasks | P4-VERIFY | Production scale, dashboard, security |
| **Phase 5** | 6 tasks | P5-VERIFY | Self-improving learning system |
| **Total** | **67 tasks** | **5 gates** | **Production-ready Minder MCP server** |

### Task Distribution

| Team Member | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Total |
|---|---|---|---|---|---|---|
| **BE** (Backend Lead) | 9 | 3 | 6 | 2 | 1 | **21** |
| **PE** (Platform Engineer) | 9 | 2 | 0 | 4 | 0 | **15** |
| **ML** (ML/RAG Engineer) | 3 | 9 | 5 | 0 | 5 | **22** |
| **FE** (Frontend/DevOps) | 0 | 0 | 0 | 5 | 0 | **5** |
| **Shared** | 1 | 1 | 1 | 1 | 1 | **5** |
