# Minder — Task Breakdown

> **Document version**: 1.3 — 2026-04-09 (post-P4.3 polish + release installer + production deploy bundle captured)
> **Status**: ACTIVE DELIVERY BASELINE

---

## Team Structure (4 Members)

| Role                         | ID   | Responsibilities                                                               |
| ---------------------------- | ---- | ------------------------------------------------------------------------------ |
| **Backend Lead**             | `BE` | Auth, data models, stores, MCP tools, workflow engine, API design              |
| **Platform Engineer**        | `PE` | Project setup, config, transport layer, Docker, CI/CD, database migrations     |
| **ML/RAG Engineer**          | `ML` | Embedding, LLM integration, LangGraph pipeline, retrieval, reranking, learning |
| **Frontend/DevOps Engineer** | `FE` | Dashboard (backend + frontend), observability, monitoring, load testing        |

## Architecture Direction Update — 2026-04-03

The project target runtime stack is now:

- **MongoDB** as the primary operational/document store, replacing the current SQLite-backed relational store.
- **Redis** as the runtime cache/session/coordination layer, delivered as a Docker image in local and deployment environments.
- **Milvus Standalone** as the vector database, replacing the previous Milvus Lite/local-file assumption.
- **Docker Compose** as the baseline deployment shape for local development and single-node environments, with explicit upgrade seams toward multi-service and clustered deployment later.

This means the current codebase should be read as:

- **Implemented baseline**: SQLite-backed operational store, local vector substrate, and Docker/dev-server scaffolding.
- **Target architecture before Phase 3 sign-off**: MongoDB + Redis + Milvus Standalone all running through Docker Compose, with config and repository abstractions shaped so Milvus can later be promoted to cluster/distributed mode without rewriting the application layer.

## Delivery Posture Update — 2026-04-09

The planning baseline is now:

- **Completed**: Phase 1, Phase 2, Phase 2.1, Phase 2.2, Phase 3, Phase 4.0, Phase 4.1, Phase 4.2, and Phase 4.3 are complete and verified.
- **Completed**: Post-P4.3 dashboard routing polish, local Astro CORS fallback, favicon plumbing, and release deployment bundle work are implemented and verified.
- **Current focus**: finish the non-scale Phase 4 product surface by prioritizing observability (`P4-T05`, `src/minder/observability/` is a confirmed-empty placeholder), broader admin/dashboard workflows (`P4-T07`–`P4-T09`), and a security hardening pass (`P4-T12`).
- **Explicitly deferred for now**: cluster-ready MongoDB/Milvus topologies, Redis HA/failover work, and formal load-testing for scale-up readiness.
- **Planning rule**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md) is the canonical status board; this file remains the canonical task catalog and prioritization reference.

---

## Phase 1 — Foundation: MCP Server, Auth, Search, CI/CD

**Goal**: Deliver a working SSE-first MCP server with auth, repo-local state, containerized stateful services, basic search, and CI/CD.

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

### Current Implementation Audit

> **Current status as of 2026-04-09**: `DONE`
>
> Phase 1 is closed. The repository now has verified SSE and stdio transports, MongoDB-backed operational persistence, Redis runtime support, Milvus Standalone integration, repository-local `.minder/` state, bootstrap scripts, Docker Compose development infrastructure, and CI/release workflows.

### Phase 1 Status Map

| Area                                            | Status | Notes                                                                                                  |
| ----------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------ |
| Core foundation tasks `P1-T01` through `P1-T22` | `DONE` | Canonical per-task completion is tracked in [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md). |
| Phase 1 acceptance gate `P1-VERIFY`             | `DONE` | Full-stack acceptance baseline is complete and tracked in the progress board.                          |
| Runtime baseline                                | `DONE` | Minder runs on MongoDB + Redis + Milvus Standalone with Compose-managed local infrastructure.          |

### Current Runnable Flow

The current baseline supports the intended Phase 1+ local runtime:

1. Start the local stack with Docker Compose.
2. Run authenticated MCP flows over SSE or stdio.
3. Use workflow, memory, search, auth, session, and query tools on the current runtime stack.
4. Verify local and acceptance behavior through the integration gates already tracked in [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md).

### Phase 1 Closure Work Still Needed

No remaining Phase 1 closure work is required. Future infrastructure changes should be tracked under the active Phase 4 backlog, not reopened under Phase 1.

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

#### P1-T04: Primary Operational Store (MongoDB)

- **Owner**: `BE`
- **Requirement**: Replace the SQLite-backed operational persistence path with MongoDB-backed repositories for User, Session, Workflow, Repository, RepositoryWorkflowState, History, Error, and Document metadata. Preserve the existing application/tool contracts while changing the infrastructure layer.
- **Result**: Operational data persists in MongoDB. CRUD and query flows work through repository adapters. Existing application-layer tests remain green with Mongo-backed implementations.

#### P1-T04A: MongoDB Repository Migration

- **Owner**: `BE` + `PE`
- **Requirement**: Add MongoDB models, indexes, config, bootstrap wiring, and a migration/backfill path from the current SQLite development dataset. Ensure Docker Compose includes a MongoDB service and app startup waits for it correctly.
- **Result**: The dev stack boots with MongoDB, repositories initialize cleanly, and migration/backfill tooling exists for local environments.

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
- **Requirement**: Implement `src/minder/embedding/qwen.py` — load `ggml-org/embeddinggemma-300M-GGUF` via `llama-cpp-python`. Generate 768-dim embeddings. Implement `src/minder/embedding/base.py` as abstract interface.
- **Result**: Text input → 768-dim vector output. Model loads from configured path. Unit test validates embedding dimensions and determinism.

#### P1-T10: Embedding Fallback (OpenAI)

- **Owner**: `ML`
- **Requirement**: Implement `src/minder/embedding/openai.py` — OpenAI `text-embedding-3-small` as optional fallback. Same interface as Qwen embedder. Auto-fallback when local model fails and OpenAI key is configured.
- **Result**: When Qwen unavailable and API key set, OpenAI embeddings are used transparently. Unit test validates fallback logic.

#### P1-T11: Vector Store (Milvus Standalone)

- **Owner**: `ML`
- **Requirement**: Replace the Milvus Lite/local-file assumption with Milvus Standalone integration. Collections for skills, documents, and errors must connect to a containerized Milvus service configured through app settings and Docker Compose.
- **Result**: Vectors insert and search correctly against Milvus Standalone. Top-K results return with scores. Threshold filtering works. Unit and integration tests cover insert, search, delete, and filtering.

#### P1-T11A: Redis Runtime Layer

- **Owner**: `BE` + `PE`
- **Requirement**: Add Redis-backed runtime capabilities for cache/session/coordination concerns. Define what state is authoritative in MongoDB vs cached in Redis, wire config and health checks, and run Redis as a Compose-managed image.
- **Result**: Redis is part of the dev stack, the app can read/write its runtime cache/session layer, and cache failure modes are explicit and testable.

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
- **Requirement**: Implement `scripts/seed_skills.py` — clone external GitHub repo, parse skills from configured path, and import embeddings into Milvus Standalone.
- **Result**: Skills from external repo are importable. Duplicates are handled. Script is idempotent. Integration test validates import.

#### P1-T18: Model Download Script

- **Owner**: `PE`
- **Requirement**: Implement `scripts/download_models.sh` — download Qwen embedding and LLM GGUF files to `~/.minder/models/`. Verify checksums. Skip if already present.
- **Result**: Models download successfully. Checksum validation passes. Re-run skips existing files.

#### P1-T19: Docker Development Stack

- **Owner**: `PE`
- **Requirement**: Create and maintain the canonical local infra compose file plus the production container images. Local Docker must provide MongoDB, Redis, and Milvus dependencies for debugging, while the application and dashboard can run locally outside Docker.
- **Result**: `docker compose -f docker/docker-compose.local.yml up` starts the local dependency stack. Minder and the dashboard can then run locally against those services.

#### P1-T20: GitHub Actions CI

- **Owner**: `PE`
- **Requirement**: Create `.github/workflows/ci.yml` — checkout, setup Python 3.14 + uv, install deps, ruff lint, mypy, unit tests, integration tests, coverage report, Docker build verification.
- **Result**: CI runs on PR and push to main. All steps pass. Coverage report generated.

#### P1-T21: GitHub Actions Release

- **Owner**: `PE`
- **Requirement**: Create `.github/workflows/release.yml` — triggered on version tags. Run full CI, build multi-arch API/dashboard Docker images, push to ghcr.io, and publish a GitHub Release with a user-facing install script and quick-start notes.
- **Result**: Tagging `v0.1.0` triggers release. API and dashboard images are published. GitHub Release includes a one-shot installer script and release guidance.

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
  5. MongoDB is the active operational store
  6. Redis is reachable and runtime cache/session operations work
  7. Memory store → semantic search → recall works through Milvus Standalone
  8. Repository-local `.minder/` state writes and restores
  9. CI pipeline passes on GitHub Actions
- **Result**: All 9 checks pass. Phase 1 is complete.

---

## Phase 2 — Agentic Pipeline: LangGraph and Guided Execution

**Goal**: Deliver end-to-end agentic pipeline with workflow-aware reasoning and Docker-based verification.

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

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
- **Requirement**: Implement `src/minder/llm/qwen.py` and `src/minder/graph/nodes/llm.py` — load `ggml-org/gemma-4-E2B-it-GGUF` via `llama-cpp-python`. Route prompts to local model by default. Stream output.
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

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

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
- **Requirement**: Replace the placeholder local LLM in `src/minder/llm/qwen.py` with real `llama-cpp-python` loading of `ggml-org/gemma-4-E2B-it-GGUF`, including streaming support and structured generation result.
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

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

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

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

### Wave Plan

| Wave       | Focus                                          | Tasks                                          | Status |
| ---------- | ---------------------------------------------- | ---------------------------------------------- | ------ |
| `P3-Wave1` | Retrieval Infrastructure                       | P3-T04, P3-T02, P3-T03, P3-T01, P3-T07, P3-T08 | `DONE` |
| `P3-Wave2` | Knowledge Graph & Extended Stores              | P3-T05, P3-T06                                 | `DONE` |
| `P3-Wave3` | Ingestion Expansion & Repo Relationships       | P3-T09, P3-T10                                 | `DONE` |
| `P3-Wave4` | MCP Resources, Prompts & Workflow Intelligence | P3-T11, P3-T12                                 | `DONE` |
| `P3-Wave5` | P3 Verification Gate                           | P3-VERIFY                                      | `DONE` |

### Tasks

---

#### Wave 1 — Retrieval Infrastructure

##### P3-T04: MMR Diversity Filtering

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/retrieval/mmr.py`
- **Requirement**: Implement Maximal Marginal Relevance — re-rank a candidate list by balancing relevance to the query against similarity to already-selected results. Configurable `lambda_mult` (0 = max diversity, 1 = max relevance). Pure-Python, no external deps.
- **Result**: Top-N results are diverse, not repetitive. Unit tests validate diversity vs. pure relevance ordering with controlled similarity matrices.

##### P3-T02: BM25 Hybrid Retrieval

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/retrieval/hybrid.py`
- **Requirement**: Implement `HybridRetriever` that combines vector-search scores with BM25 keyword scores. Configurable `alpha` (0 = pure BM25, 1 = pure vector). BM25 implemented in pure Python (no external index server). Normalized RRF or linear blend.
- **Result**: Hybrid search improves recall for keyword-heavy queries versus pure vector search. Unit tests validate alpha=0, alpha=1, and alpha=0.5 blending with synthetic documents.

##### P3-T03: Multi-Hop Retrieval

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/retrieval/multi_hop.py`
- **Requirement**: Implement `MultiHopRetriever` — first hop retrieves top-K candidates; second hop generates an expanded query from first-hop content, then retrieves again and merges de-duplicated results. Max hops configurable (default 2).
- **Result**: Multi-hop returns documents unreachable by single-hop when the link is only visible via intermediate content. Unit tests validate iterative refinement with a stub retriever.

##### P3-T01: Reranking (Cross-Encoder)

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/graph/nodes/reranker.py`
- **Requirement**: Implement `RerankerNode` — takes `state.retrieved_docs`, scores each document against the query using cosine similarity (real `sentence-transformers` cross-encoder when available, else mock score passthrough). Applies MMR after scoring. Writes `state.reranked_docs`. Integrates into graph between Retriever and Reasoning nodes.
- **Result**: `state.reranked_docs` is more relevant and diverse than raw `state.retrieved_docs`. Unit tests cover real path (monkeypatch) and mock fallback. Graph integration test confirms node fires between retriever and reasoning.

##### P3-T07: AST-Aware Code Chunking

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/chunking/code_splitter.py`
- **Requirement**: Implement `CodeSplitter` — parse Python source into AST, chunk by top-level function/class boundaries. Prepend module-level imports to each chunk for self-containedness. TypeScript and Java: fallback to line-based splitting at `{`/`}` depth=0 boundaries. Return list of `CodeChunk(content, start_line, end_line, symbol_name, language)`.
- **Result**: Python chunks align with `def`/`class` boundaries with imports preserved. Unit tests validate Python (real AST), TypeScript (line-based), and Java (line-based).

##### P3-T08: Text Chunking

- **Wave**: `P3-Wave1`
- **Status**: `DONE`
- **Owner**: `ML`
- **File**: `src/minder/chunking/splitter.py`
- **Requirement**: Implement `TextSplitter` — sliding-window chunking with configurable `chunk_size` (default 512 tokens estimated by char/4) and `overlap` (default 64). Markdown-aware: prefer split at heading boundaries when possible. Returns list of `TextChunk(content, start_char, end_char)`.
- **Result**: Documents chunk at heading boundaries when possible. Overlap preserves context across chunks. Unit tests validate size constraints, overlap, and markdown heading splitting.

---

#### Wave 2 — Knowledge Graph & Extended Stores

##### P3-T05: Knowledge Graph Store

- **Wave**: `P3-Wave2`
- **Status**: `DONE`
- **Owner**: `BE`
- **File**: `src/minder/store/graph.py`
- **Requirement**: Implement `KnowledgeGraphStore` backed by SQLite (dev) / MongoDB (prod). Entities: nodes with `id`, `type` (module, service, file, owner), `name`, `metadata`. Edges: `source_id`, `target_id`, `relation` (depends_on, owns, imports, calls), `weight`. Methods: `add_node`, `add_edge`, `get_node`, `get_neighbors`, `get_path`, `query_by_type`, `upsert_node`. Add SQLAlchemy models (`GraphNode`, `GraphEdge`) to `models/`.
- **Result**: Nodes and edges store and query correctly. Neighbor traversal and type queries work. Unit tests cover CRUD, traversal, and upsert idempotence.

##### P3-T06: Rule and Feedback Stores

- **Wave**: `P3-Wave2`
- **Status**: `DONE`
- **Owner**: `BE`
- **Files**: `src/minder/store/rule.py`, `src/minder/store/feedback.py`
- **Requirement**: `RuleStore` — CRUD for `Rule` SQLAlchemy model (already in `models/rule.py`); `list_by_scope(scope)`, `list_active()`. `FeedbackStore` — add `Feedback` SQLAlchemy model (schema in `models/rule.py` as `FeedbackSchema`); CRUD + `list_by_entity(entity_type, entity_id)`, `average_rating(entity_id)`. Both wired into `RelationalStore` and `IOperationalStore` interface.
- **Result**: Rules filter by scope and active flag. Feedback aggregates rating per entity. Unit tests cover all methods.

---

#### Wave 3 — Ingestion Expansion & Repository Relationships

##### P3-T09: Ingestion Tools Expansion

- **Wave**: `P3-Wave3`
- **Status**: `DONE`
- **Owner**: `BE`
- **File**: `src/minder/tools/ingest.py`
- **Requirement**: Add `minder_ingest_url` — fetch via `httpx`, detect content type, chunk via `TextSplitter`, embed, upsert to document store. Add `minder_ingest_git` — shallow `git clone` to temp dir, call `minder_ingest_directory`, cleanup. Both use the same chunk→embed→store pipeline as existing methods.
- **Result**: URLs and git repos ingest end-to-end through the unified pipeline. Integration test validates ingestion and retrieval of URL and git content.

##### P3-T10: Repository Relationship Tracking

- **Wave**: `P3-Wave3`
- **Status**: `DONE`
- **Owner**: `BE`
- **File**: `src/minder/tools/repo_scanner.py`
- **Requirement**: Implement `RepoScanner` — walk repository, parse Python `import` statements via AST, identify module→module dependency edges. Detect service boundaries via `pyproject.toml` / `package.json` presence. Write discovered nodes (file, module) and edges (imports, depends_on) into `KnowledgeGraphStore`. Re-scan is idempotent (upsert).
- **Result**: Scanning a Python repo produces a graph of module import relationships. Re-scan updates existing nodes/edges without duplicates. Unit tests validate scan output against a synthetic fixture repo.

---

#### Wave 4 — MCP Resources, Prompts & Workflow Intelligence

##### P3-T11: MCP Resources and Prompts

- **Wave**: `P3-Wave4`
- **Status**: `DONE`
- **Owner**: `BE`
- **Files**: `src/minder/resources/__init__.py`, `src/minder/prompts/__init__.py`
- **Requirement**: Resources: `skills` (list all skills with title/tags), `repos` (list repos with workflow state), `stats` (query count, avg latency, error rate from history). Prompts: `debug` (structured debug prompt template), `review` (code review checklist template), `explain` (explain code template), `tdd_step` (TDD step guidance injecting current workflow step). Register resources and prompts via transport's MCP `app` object.
- **Result**: MCP client can call `resources/list`, `resources/read`, `prompts/list`, `prompts/get`. Integration test validates all 4 resources and 4 prompt templates are accessible.

##### P3-T12: Workflow Intelligence Enhancement

- **Wave**: `P3-Wave4`
- **Status**: `DONE`
- **Owner**: `BE` + `ML`
- **File**: `src/minder/graph/nodes/workflow_planner.py`
- **Requirement**: Extend `WorkflowPlannerNode.run()` to optionally query `KnowledgeGraphStore` for the current repo — retrieve module dependencies, failing test artifacts, and ownership relationships. Inject dependency-aware context into `state.workflow_context["guidance"]`. Gracefully no-ops when graph store is not provided (backwards compatible).
- **Result**: When graph store is present, workflow guidance includes dependency context such as "Module X imports Y which has unresolved guard failures." Unit tests validate enriched guidance with a stub graph store and that the node still runs without a graph store.

---

#### Wave 5 — P3 Verification Gate

##### P3-VERIFY: Phase 3 Acceptance Test

- **Wave**: `P3-Wave5`
- **Status**: `DONE`
- **Owner**: `ML` + `BE`
- **File**: `tests/integration/test_phase3_gate.py`
- **Requirement**: Write and run `tests/integration/test_phase3_gate.py` validating all Wave 1–4 deliverables:
  1. MMR produces more diverse results than raw cosine ranking
  2. Hybrid search (alpha=0.5) outperforms pure vector search MRR@5 on keyword-heavy queries
  3. Multi-hop retrieval finds documents reachable only via intermediate content
  4. Reranker node fires and `reranked_docs` differs from `retrieved_docs` when duplicates present
  5. Code splitter chunks Python at function/class boundaries with imports preserved
  6. Text splitter respects chunk size and overlap constraints
  7. Knowledge graph stores nodes + edges and traversal returns correct neighbors
  8. Rule store filters by scope; feedback store aggregates rating
  9. `minder_ingest_url` and `minder_ingest_git` complete without error on synthetic inputs
  10. Repo scanner produces import-graph edges for a synthetic Python fixture
  11. MCP resources `skills`, `repos`, `stats` are accessible via transport
  12. MCP prompts `debug`, `review`, `explain`, `tdd_step` render correctly
  13. Workflow guidance includes dependency context when graph store is provided
- **Result**: All 13 checks pass. Phase 3 is complete.

---

## Phase 4 — Production Scale, Multi-User, Dashboard

**Goal**: Production-ready for teams with a dashboard for workflow administration.

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

**Phase 4.0 design doc**: [`docs/design/mcp-gateway-auth-dashboard.md`](../docs/design/mcp-gateway-auth-dashboard.md)

**Phase 4.3 requirements doc**: [`docs/requirements/p4_3_console_clean_architecture_and_ui_modernization.md`](../docs/requirements/p4_3_console_clean_architecture_and_ui_modernization.md)

**Phase 4.3 design doc**: [`docs/design/p4_3_console_clean_architecture_and_ui_modernization.md`](../docs/design/p4_3_console_clean_architecture_and_ui_modernization.md)

### Current Delivery Posture — 2026-04-09

#### Completed baseline

- `P4.0`, `P4.1`, `P4.2`, and `P4.3` are complete.
- The dashboard setup, login, client registry, client detail, onboarding snippets, connection testing, and clean-architecture refactor are all in place.
- `P4-T04` rate limiting is complete.

#### Active next-step scope

1. `P4-T05` Observability Stack
2. `P4-T07` Dashboard Backend API expansion for workflow, repository, and user administration
3. `P4-T08` and `P4-T09` workflow/repository/user dashboard surfaces
4. `P4-T10` observability UI after the backend metrics/audit surface exists
5. `P4-T12` focused security review after the observability and admin surface stabilize

#### Explicitly deferred until needed

- `P4-T01` MongoDB production topology upgrade
- `P4-T02` Milvus cluster upgrade path
- `P4-T03` Redis HA cache layer
- `P4-T06` production Docker Compose hardening
- `P4-T11` formal load testing for scale-up readiness

#### Planning note

The deferred items remain part of the long-term catalog, but they are not the current delivery path. The next implementation slice should optimize for operability and admin product completeness, not cluster readiness.

### Phase 4.0 — MCP Gateway Auth and Dashboard Foundation

**Goal**: Remove the current MCP onboarding friction by introducing a client-aware gateway model, token exchange, and an admin dashboard for client/API key management.

#### P4.0-T01: Client Registry Domain

- **Owner**: `BE`
- **Requirement**: Add durable domain models and repository contracts for `Client`, `ClientApiKey`, `ClientSession`, and `AuditLog`. Support status, scopes, repo constraints, creator metadata, and key lifecycle state.
- **Result**: Machine clients become a first-class concept in the domain model without breaking the current user-oriented auth flow.

#### P4.0-T02: Token Exchange API

- **Owner**: `BE`
- **Requirement**: Implement `POST /v1/auth/token-exchange` to exchange a client API key for a short-lived access token. Add expiry, revoke, and optional refresh semantics.
- **Result**: MCP clients can bootstrap access without manually calling `minder_auth_login`.

#### P4.0-T03: Principal-Based Gateway Auth

- **Owner**: `BE`
- **Requirement**: Evolve the transport/auth layer from a `User` assumption to a `Principal` abstraction that supports `AdminUserPrincipal` and `ClientPrincipal`. Enforce tool and repo scopes per principal.
- **Result**: Authenticated tool calls can be attributed and authorized for both humans and machine clients.

#### P4.0-T04: Redis-Backed Client Session Layer

- **Owner**: `BE` + `PE`
- **Requirement**: Use Redis for short-lived client access token/session state, revocation checks, and exchange throttling. Keep MongoDB as the durable metadata source of truth.
- **Result**: Client auth remains fast on hot paths and revocation semantics are explicit.

#### P4.0-T05: Dashboard Backend for Client Management

- **Owner**: `FE`
- **Requirement**: Add backend endpoints for admin login, client CRUD, API key issue/revoke/rotate, audit queries, health checks, and connection testing.
- **Result**: The dashboard has a backend contract that can fully manage machine clients and their credentials.

#### P4.0-T06: Dashboard Frontend for Client/API Key Management

- **Owner**: `FE`
- **Requirement**: Build the initial admin UI shell for login, dashboard session handling, setup context, and a lightweight client registry view. This establishes the dashboard surface but does not require full CRUD forms in the first slice.
- **Result**: Admins can sign in and reach a dashboard shell that is ready for later client-management UI waves.

#### P4.0-T07: MCP Onboarding Templates

- **Owner**: `FE`
- **Requirement**: Provide copy-paste onboarding templates and connection guidance for Codex, VS Code Copilot-style MCP clients, Claude Desktop, and generic MCP consumers.
- **Result**: External clients can connect using dashboard instructions alone.

#### P4.0-T08: Audit and Revocation Hardening

- **Owner**: `BE`
- **Requirement**: Record token exchange, auth failures, tool usage, revocations, and scope denials with enough detail for incident review and support.
- **Result**: Every client action is attributable and revocation is observable.

#### P4.0-VERIFY: End-to-End MCP Client Onboarding Gate

- **Owner**: `BE` + `FE` + `PE`
- **Requirement**: Add `tests/e2e/test_phase4_gateway_auth.py` and manual dashboard verification that prove:
  1. Admin can sign into the dashboard
  2. Admin can create a client and issue an API key
  3. A client can exchange API key for access token
  4. A protected MCP tool call succeeds without manual login choreography
  5. Revocation blocks further access
  6. Audit logs capture the full flow
- **Result**: Phase 4.0 is complete and external MCP onboarding becomes simple enough for real team usage.

### Phase 4.1 — Dashboard Initialization & Plug-and-Play MCP Auth

**Goal**: Remove manual setup script dependencies by providing a first-time dashboard setup wizard, an admin API-key recovery mechanism, and a seamless zero-exchange API key auth flow for static MCP clients like Claude Desktop.

#### P4.1-T01: First-Time Setup Wizard (Dashboard)

- **Owner**: `FE` + `BE`
- **Requirement**: If no admin users exist in the database, the dashboard root must redirect to `/setup` to collect the initial admin username, email, and display name. On success, the setup flow must create the first admin and reveal the bootstrap API key exactly once. After creation, this route must be disabled.
- **Result**: A fresh Docker deployment can be initialized entirely via the browser.

#### P4.1-T02: CLI Admin API-Key Recovery

- **Owner**: `PE`
- **Requirement**: Add `scripts/reset_admin_api_key.py` that locates an existing admin user, rotates the admin API key securely, invalidates prior admin API-key access for that target account, and records the action in audit history.
- **Result**: Admins can recover access using container exec execution without writing raw DB queries.

#### P4.1-T03: Direct API Key Auth (Plug & Play)

- **Owner**: `BE`
- **Requirement**: Update the Auth Middleware and Base Transport to accept `X-Minder-Client-Key` (for SSE/HTTP) and equivalent env injection (for stdio). These keys must be validated directly against the Redis/DB layer and resolved to a `ClientPrincipal` without forcing the client to call `/v1/auth/token-exchange`.
- **Result**: Static clients like Claude Desktop or Cursor can connect using just the raw API key generated from the dashboard.

#### P4.1-VERIFY: Plug-and-Play Gate

- **Owner**: `BE` + `FE`
- **Requirement**: Update or add integration tests that prove the setup wizard flow works, admin API-key recovery updates the account access path, and an MCP client can invoke a protected tool by directly supplying the raw API key in the connection header/env.
- **Result**: Phase 4.1 is complete. Administrator and Client onboarding are both fully frictionless.

### Phase 4.2 — Client Management Dashboard UI

**Goal**: Close the remaining browser UX gap by adding a real dashboard interface for creating and managing MCP clients, API keys, scopes, and onboarding snippets without dropping to raw admin HTTP calls.

#### P4.2-T01: Client Registry Screen

- **Owner**: `FE`
- **Requirement**: Expand `/dashboard` into a real client registry page that lists existing clients, status, scopes, transport modes, and recent key activity. Keep the current server-rendered baseline if possible, but make the page actionable rather than informational only.
- **Result**: Admins can inspect all configured MCP clients from the browser.

#### P4.2-T02: Create Client Form

- **Owner**: `FE` + `BE`
- **Requirement**: Add a browser form for creating a client with name, slug, description, tool scopes, repo scopes, and transport preferences. The form must POST through the existing admin backend contract and show the newly issued `client_api_key` exactly once after creation.
- **Result**: A new MCP client can be created entirely from the browser with no manual `curl` step.

#### P4.2-T03: Client Detail and Key Management UI

- **Owner**: `FE`
- **Requirement**: Add a client detail view with actions to rotate/revoke keys, inspect allowed scopes, and show audit-relevant lifecycle metadata. Reuse the existing backend endpoints for key creation and revocation.
- **Result**: Admins can manage a client lifecycle entirely from the browser.

#### P4.2-T04: Onboarding Snippets and Copy UX

- **Owner**: `FE`
- **Requirement**: Surface the existing onboarding templates in the dashboard with copy-ready snippets for Codex, Copilot-style MCP, Claude Desktop, and stdio bootstrapping. Include transport-specific instructions for `X-Minder-Client-Key`, `MINDER_CLIENT_API_KEY`, and optional token exchange.
- **Result**: A newly created client can be onboarded from dashboard instructions alone.

#### P4.2-T05: Dashboard Connection Test and Activity Surface

- **Owner**: `FE` + `BE`
- **Requirement**: Expose the existing connection-test endpoint and recent audit/activity data inside the dashboard so an operator can validate a client immediately after creation.
- **Result**: The dashboard can confirm that a client is configured correctly and show the latest onboarding-relevant events.

#### P4.2-VERIFY: Client Management Dashboard Gate

- **Owner**: `FE` + `BE`
- **Requirement**: Add end-to-end tests and manual verification that prove:
  1. Admin signs into `/dashboard/login`
  2. Admin creates a client from the browser UI
  3. The dashboard reveals the new `client_api_key` exactly once
  4. The dashboard renders onboarding snippets for that client
  5. The admin can revoke or rotate a key from the browser
  6. Recent activity in the dashboard reflects create and revoke events
- **Result**: Browser-only client onboarding is complete.

### Phase 4.3 — Console Clean Architecture and UI Modernization

**Goal**: Refactor the current web console out of the one-file `src/minder/server.py` shape, enforce clean architecture boundaries for the admin/backend surface, and migrate the dashboard UI to a maintainable frontend framework.

#### P4.3-T01: Server Composition Root Extraction

- **Owner**: `BE`
- **Requirement**: Reduce `src/minder/server.py` to bootstrap/composition only. Move store/cache/vector/transport assembly into `bootstrap` modules and move admin HTTP route registration out of the entrypoint file.
- **Result**: `server.py` is no longer the home for route handlers, HTML rendering, or dashboard flow logic.

#### P4.3-T02: Admin Presentation Layer Split

- **Owner**: `BE`
- **Requirement**: Extract admin HTTP routes, controllers, DTO parsing, cookie/session handling, and redirect/view-model mapping into dedicated presentation modules under `src/minder/presentation/http/`.
- **Result**: Browser/admin HTTP behavior is isolated from application logic and framework wiring.

#### P4.3-T03: Admin Application Use Cases

- **Owner**: `BE`
- **Requirement**: Create explicit use cases for setup, login/logout, list clients, create client, get client detail, issue key, revoke key, test connection, and recent activity. Controllers may call only these use cases, not infrastructure directly.
- **Result**: Console business flows conform to clean architecture and become testable without route-level coupling.

#### P4.3-T04: Stable Admin API Contract

- **Owner**: `BE` + `FE`
- **Requirement**: Normalize the admin/browser surface around typed JSON APIs that the new dashboard can consume. Keep existing auth and client-management semantics, but remove backend dependence on inline HTML rendering.
- **Result**: The browser console can evolve independently from the Python presentation layer.

#### P4.3-T05: Astro Dashboard Shell

- **Owner**: `FE`
- **Requirement**: Introduce `src/dashboard/` using `Astro` + `TypeScript` + `Tailwind CSS`, with lightweight interactive islands only where needed. Add the shell for setup, login, client list, and client detail pages, and plan it to build into static assets that the Python app can serve from `/dashboard`.
- **Result**: Dashboard UI moves onto a maintainable frontend stack without requiring a separate always-on frontend runtime.

#### P4.3-T06: Client Management UI Migration

- **Owner**: `FE`
- **Requirement**: Migrate current browser features from the Python-rendered console into the new dashboard: create client, scope selection, onboarding snippets, rotate/revoke key, connection test, and recent activity.
- **Result**: Feature parity is reached on the new dashboard UI.

#### P4.3-T07: Legacy Console Decommission

- **Owner**: `BE` + `FE`
- **Requirement**: Remove or hard-disable the legacy HTML dashboard rendering path after parity is verified. Keep only MCP runtime, admin APIs, and bootstrap/composition responsibilities in the Python service.
- **Result**: The old one-file console is no longer part of the production path.

#### P4.3-VERIFY: Clean Console Parity Gate

- **Owner**: `BE` + `FE`
- **Requirement**: Add backend and browser end-to-end verification that prove:
  1. `src/minder/server.py` is reduced to composition/bootstrap responsibilities
  2. admin HTTP flows go through controllers and use cases
  3. the new dashboard setup/login/client-management flow works from the Astro frontend
  4. current client-management features have no regression
  5. the legacy HTML console path is removed or isolated behind an explicit temporary compatibility seam
- **Result**: Phase 4.3 is complete and the console now follows clean architecture with a maintainable UI stack.

### Tasks

#### P4-T01: MongoDB Production Topology Upgrade

- **Owner**: `PE`
- **Requirement**: Upgrade the MongoDB deployment path from single-node dev usage to production-ready topology options such as replica set and, later, sharded deployment. Add operational scripts, readiness checks, backup/restore guidance, and environment-specific config.
- **Result**: All operational data flows work on the production MongoDB topology. Rollout and recovery procedures are documented and tested.

#### P4-T02: Milvus Cluster Upgrade Path

- **Owner**: `PE`
- **Requirement**: Evolve the vector store deployment from Milvus Standalone to a cluster-ready topology. Keep the application contract stable while introducing config, deployment, and migration guidance for larger datasets and higher concurrency.
- **Result**: Vector operations continue to work while the deployment can be promoted from Milvus Standalone to clustered Milvus without application-layer rewrites.

#### P4-T03: Redis HA Cache Layer

- **Owner**: `PE`
- **Requirement**: Extend the Phase 1 Redis runtime layer toward production-ready operation: persistence settings, eviction strategy, health checks, failover strategy, and cache/session usage policies. Keep `cache.provider = "redis"` configurable across environments.
- **Result**: Cache hit avoids re-computation. TTL expiry works. Redis runtime behavior is production-documented and tested under failure scenarios.

#### P4-T04: Rate Limiting and Quotas

- **Owner**: `BE`
- **Requirement**: Implement `src/minder/auth/rate_limiter.py` — per-user rate limiting on MCP tool calls. Configurable limits by role. Quota tracking.
- **Result**: Exceeding rate limit returns 429. Admin has higher limits. Quota is tracked. Unit tests cover rate limiting.

#### P4-T05: Observability Stack

- **Owner**: `FE`
- **Status**: `NOT STARTED` — `src/minder/observability/` exists as an empty placeholder directory.
- **Requirement**: Implement `src/minder/observability/` — OpenTelemetry tracing, Prometheus metrics, structured JSON logging, audit trails for auth and workflow events.
- **Planned files**:
  - `src/minder/observability/__init__.py` — module exports
  - `src/minder/observability/tracing.py` — OpenTelemetry SDK init, tracer factory, span decorators for graph nodes and transport handlers
  - `src/minder/observability/metrics.py` — Prometheus `Counter`/`Histogram`/`Gauge` registry; expose via `/metrics` route
  - `src/minder/observability/logging.py` — structured JSON log formatter, request-scoped correlation ID middleware
  - `src/minder/observability/audit.py` — durable audit event emitter wired to the existing `AuditLog` MongoDB model; replaces ad-hoc audit calls in auth/workflow paths
- **Wire-up**: Bootstrap in `src/minder/bootstrap/providers.py`; mount `/metrics` in `src/minder/presentation/http/admin/routes.py`.
- **Result**: Traces flow through pipeline. Metrics exposed at `/metrics`. Audit log records all auth and workflow events. Integration test validates tracing.

#### P4-T06: Production Docker Compose

- **Owner**: `PE`
- **Requirement**: Create `docker/docker-compose.yml` as the image-only production runtime and `docker/docker-compose.full.yml` as the build-from-source variant. Add a release installer script that fetches the tagged compose/Caddy bundle from GitHub and starts the full stack from published images.
- **Result**: Users can either run the image-only production stack directly or execute a one-shot installer from the GitHub Release page. Source builds remain available through `docker/docker-compose.full.yml`.

#### P4-T07: Dashboard Backend API

- **Owner**: `FE`
- **Requirement**: Implement `dashboard/backend/` — FastAPI app with endpoints for workflow CRUD, repo policies, user management, metrics, audit logs, CI/CD status. Auth via Minder JWT.
- **Result**: All CRUD endpoints work. Auth enforces admin role. Integration tests validate all endpoints.

#### P4-T08: Dashboard Frontend — Workflow Management

- **Owner**: `FE`
- **Requirement**: Build `src/dashboard/` — Astro app with Tailwind CSS and interactive islands where needed. Pages: workflow list, workflow editor (step order, gate config), workflow assignment to repos.
- **Result**: Admin creates/edits workflows in UI. Workflows assign to repos. UI validates step order.

#### P4-T09: Dashboard Frontend — Repository & User Management

- **Owner**: `FE`
- **Requirement**: Extend the Astro dashboard with pages for repo list with workflow state and progress, user management (CRUD, API key rotation, role assignment), and blocked items view.
- **Result**: Admin sees repo progress, manages users, views blocked items. All CRUD operations work through UI.

#### P4-T10: Dashboard Frontend — Observability

- **Owner**: `FE`
- **Requirement**: Extend the Astro dashboard with pages for metrics dashboard (latency, success rates, usage), audit log viewer, and CI/CD status integration.
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
  5. MongoDB, Redis, and Milvus deployment choices handle production load
  6. Security review passes with no critical findings
- **Result**: All 6 checks pass. Phase 4 is complete.

---

## Phase 5 — Learning and Self-Improvement

**Goal**: Let Minder learn from workflows, failures, and feedback to improve over time.

**Progress tracker**: [`docs/PROJECT_PROGRESS.md`](../docs/PROJECT_PROGRESS.md)

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

| Phase       | Tasks        | Verification | Key Deliverable                                                            |
| ----------- | ------------ | ------------ | -------------------------------------------------------------------------- |
| **Phase 1** | 24 tasks     | P1-VERIFY    | Working MCP server with auth, search, workflow, containerized infra, CI/CD |
| **Phase 2** | 15 tasks     | P2-VERIFY    | Full LangGraph agentic pipeline with verification                          |
| **Phase 3** | 12 tasks     | P3-VERIFY    | Advanced retrieval, knowledge graph, ingestion                             |
| **Phase 4** | 28 tasks     | P4-VERIFY    | Production scale, dashboard, security, MCP gateway auth onboarding         |
| **Phase 5** | 6 tasks      | P5-VERIFY    | Self-improving learning system                                             |
| **Total**   | **85 tasks** | **5 gates**  | **Production-ready Minder MCP server**                                     |

### Task Distribution

| Team Member                | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Total  |
| -------------------------- | ------- | ------- | ------- | ------- | ------- | ------ |
| **BE** (Backend Lead)      | 9       | 3       | 6       | 2       | 1       | **21** |
| **PE** (Platform Engineer) | 9       | 2       | 0       | 4       | 0       | **15** |
| **ML** (ML/RAG Engineer)   | 3       | 9       | 5       | 0       | 5       | **22** |
| **FE** (Frontend/DevOps)   | 0       | 0       | 0       | 5       | 0       | **5**  |
| **Shared**                 | 1       | 1       | 1       | 1       | 1       | **5**  |
