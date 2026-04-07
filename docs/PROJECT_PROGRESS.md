# Minder — Project Progress

> **Purpose**: single control board for tracking delivery progress across the whole project
> **Last updated**: 2026-04-07 (P3-Wave4 complete — 231/231 unit tests pass)

---

## Project Overview

| Phase | Goal | Status | Current wave | Main blocker | Notes |
|---|---|---|---|---|---|
| `Phase 1` | Foundation: MCP server, auth, search, CI/CD | `DONE` | `foundation closed` | - | All tasks verified: SQLite init ordering fixed, stdio stdout isolation fixed, full round-trip tests pass. |
| `Phase 2` | Agentic pipeline: reasoning, retrieval, verification | `DONE` | `pipeline closed` | - | Full pipeline implemented and verified; runtime fidelity via auto-detect + monkeypatch tests. |
| `Phase 2.1` | Runtime fidelity and orchestration replacement | `DONE` | `closed` | - | LangGraph/llama_cpp/LiteLLM all tested via monkeypatch; auto-detect runtime with graceful fallback. Provisioning is ops concern. |
| `Phase 2.2` | Verification, retrieval, and workflow closure | `DONE` | `closed` | - | gate test passes; retrieval, ingest, verification, workflow contracts fully implemented. |
| `Phase 3` | Advanced retrieval, knowledge graph, process intelligence | `IN PROGRESS` | `Wave 5 — P3 Verification Gate` | - | Wave 1+2+3+4 complete: retrieval infra + graph/rule/feedback stores + ingest_url/ingest_git/RepoScanner + MCP resources/prompts + WorkflowPlannerNode graph enrichment — 231 unit tests pass. |
| `Phase 4` | Production scale, multi-user, dashboard | `NOT STARTED` | `backlog` | Depends on Phase 3 and production deployment choices | Planning exists only in breakdown docs. |
| `Phase 5` | Learning and self-improvement | `NOT STARTED` | `backlog` | Depends on reliable history/feedback foundation | Planning exists only in breakdown docs. |

---

## Phase 1 Tracker

| Task | Owner | Wave | Status | Blocker | Last update |
|---|---|---|---|---|---|
| `P1-T01` Project Initialization | `PE` | `done` | `DONE` | `-` | `Python 3.14 baseline verified` |
| `P1-T02` Configuration System | `PE` | `done` | `DONE` | `-` | `Config tests passing` |
| `P1-T03` Data Models | `BE` | `done` | `DONE` | `-` | `Model coverage in place` |
| `P1-T04` Primary Operational Store (MongoDB) | `BE` | `done` | `DONE` | `-` | `Target changed from SQLite to MongoDB` |
| `P1-T04A` MongoDB Repository Migration | `BE/PE` | `done` | `DONE` | `-` | `Completed domain interfaces and adapters tests` |
| `P1-T05` Auth Layer | `BE` | `done` | `DONE` | `-` | `JWT/RBAC/API key flow implemented` |
| `P1-T06` SSE Transport | `1` | `DONE` | `-` | `SSE server lifecycle and session management implemented` |
| `P1-T07` Stdio Transport | `1` | `DONE` | `-` | `Full JSON-RPC stdio lifecycle verified via test_phase1_stdio_roundtrip.py` |
| `P1-T08` Auth Middleware for SSE | `1` | `DONE` | `-` | `ASGI body-injection auth bridging implemented and verified` |
| `P1-T09` Embedding Layer (Qwen GGUF) | `done` | `DONE` | `-` | `auto-detect runtime (llama_cpp if available, else mock); both paths unit-tested via monkeypatch` |
| `P1-T10` Embedding Fallback (OpenAI) | `done` | `DONE` | `-` | `Fallback provider exists` |
| `P1-T11` Vector Store (Milvus Standalone) | `done` | `DONE` | `-` | `Milvus integration and search/upsert implemented` |
| `P1-T11A` Redis Runtime Layer | `done` | `DONE` | `-` | `Redis and LRU fallback providers implemented` |
| `P1-T12` Repository-Local State Management | `2` | `DONE` | `-` | `Wave 2 repo-state store + integration test completed` |
| `P1-T13` Workflow Engine (Basic) | `2` | `DONE` | `-` | `Full SSE round-trip coverage implemented` |
| `P1-T14` Memory & Search Tools (Basic) | `2` | `DONE` | `-` | `Memory/search modules + integration test completed` |
| `P1-T15` Auth MCP Tools | `2` | `DONE` | `-` | `Full SSE round-trip coverage with auth bridging verified` |
| `P1-T16` Session Tools | `2` | `DONE` | `-` | `Full SSE round-trip coverage with auth bridging verified` |
| `P1-T17` Skill Seeding | `3` | `DONE` | `-` | `Local seeding, idempotence, and git clone path all covered via test_seed_skills_script_git_clone_path` |
| `P1-T18` Model Download Script | `done` | `DONE` | `-` | `Skip/checksum contract implemented and verified` |
| `P1-T19` Docker Development Stack | `done` | `DONE` | `-` | `Compose expanded with MongoDB + Redis + Milvus Stack` |
| `P1-T20` GitHub Actions CI | `3` | `DONE` | `-` | `ci.yml modernized with parallelized jobs and Makefile integration` |
| `P1-T21` GitHub Actions Release | `3` | `DONE` | `-` | `release.yml updated with Makefile targets for consistency` |
| `P1-T22` Admin Creation Script | `3` | `DONE` | `-` | `Idempotent create_admin contract implemented and tested` |
| `P1-VERIFY` Phase 1 Acceptance Test | `done` | `DONE` | `-` | `Gate re-baselined for full stack via infrastructure fixtures` |

## Architecture Reset — 2026-04-03

| Area | Current baseline | Target before Phase 3 | Tracking implication |
|---|---|---|---|
| Operational store | `MongoDB` | `MongoDB` | Completed |
| Runtime cache/session | `Redis / LRU` | `Redis` | Completed |
| Vector store deployment | `Milvus Standalone` | `Milvus Standalone` | Completed |
| Local deployment shape | `Compose-managed full stack` | `Compose-managed multi-service stack` | Completed |

## Recommended Next Waves

| Wave | Focus | Tasks | Status |
|---|---|---|---|
| `Wave 8` | ~~SSE/Stdio real round-trip tests~~ | `CLOSED` — all transport round-trips verified 2026-04-06 | `DONE` |
| `P3-Wave1` | Retrieval Infrastructure | `P3-T04` MMR, `P3-T02` BM25 hybrid, `P3-T03` multi-hop, `P3-T01` reranker, `P3-T07` code chunking, `P3-T08` text chunking | `DONE` |
| `P3-Wave2` | Knowledge Graph & Extended Stores | `P3-T05` graph store, `P3-T06` rule + feedback stores, wire interfaces | `DONE` |
| `P3-Wave3` | Ingestion Expansion & Repo Relationships | `P3-T09` ingest_url + ingest_git, `P3-T10` relationship tracking | `DONE` |
| `P3-Wave4` | MCP Resources, Prompts & Workflow Intelligence | `P3-T11` resources + prompts, `P3-T12` workflow enrichment | `DONE` |
| `P3-Wave5` | P3 Verification Gate | `P3-VERIFY` test_phase3_gate.py | `UP NEXT` |

---

## Phase 2 Snapshot

| Area | Status | Notes |
|---|---|---|
| Graph pipeline and nodes | `DONE` | State, planner, retriever, reasoning, LLM, guard, verification, evaluator exist. |
| Query/search tool surface | `DONE` | `minder_query`, code search, error search exist and are tested. |
| History/error persistence | `DONE` | Stores and recording flow exist. |
| Acceptance gate baseline | `DONE` | `tests/integration/test_phase2_gate.py` passes. |

## Phase 2.x Snapshot

| Area | Status | Notes |
|---|---|---|
| LangGraph adapter path | `DONE` | Adapter + monkeypatch test for StateGraph confirmed; graceful internal fallback when langgraph absent. |
| llama_cpp local runtime | `DONE` | auto-detect; real llama_cpp path unit-tested via monkeypatch; mock fallback for CI. |
| LiteLLM fallback path | `DONE` | auto-detect; real litellm path unit-tested via monkeypatch; mock fallback for CI. |
| Repo ingest + retrieval substrate | `DONE` | Ingest and vector-backed retrieval are implemented. |
| Verification contract | `DONE` | Docker/subprocess contract and failure classification are implemented. |
| Phase 2.x gate | `DONE` | `tests/integration/test_phase2x_gate.py` passes. |

## Phase 3 Tracker

| Task | Wave | Status | Blocker | Notes |
|---|---|---|---|---|
| `P3-T01` Reranking (Cross-Encoder) | `P3-Wave1` | `DONE` | - | `src/minder/graph/nodes/reranker.py`; cross-encoder→MMR→passthrough; wired in executor + graph |
| `P3-T02` BM25 Hybrid Retrieval | `P3-Wave1` | `DONE` | - | `src/minder/retrieval/hybrid.py`; pure-Python BM25, alpha-blended with vector scores |
| `P3-T03` Multi-Hop Retrieval | `P3-Wave1` | `DONE` | - | `src/minder/retrieval/multi_hop.py`; iterative query expansion, dedup by path, hop tagging |
| `P3-T04` MMR Diversity Filtering | `P3-Wave1` | `DONE` | - | `src/minder/retrieval/mmr.py`; pure-Python greedy MMR, score fallback when no embeddings |
| `P3-T05` Knowledge Graph Store | `P3-Wave2` | `DONE` | - | `src/minder/store/graph.py`; `models/graph.py`; add_node/edge, upsert, BFS traversal, get_path |
| `P3-T06` Rule + Feedback Stores | `P3-Wave2` | `DONE` | - | `store/rule.py`, `store/feedback.py`; Feedback ORM added; wired into RelationalStore + IOperationalStore |
| `P3-T07` AST-Aware Code Chunking | `P3-Wave1` | `DONE` | - | `src/minder/chunking/code_splitter.py`; Python ast + brace-depth for TS/Java |
| `P3-T08` Text Chunking | `P3-Wave1` | `DONE` | - | `src/minder/chunking/splitter.py`; markdown-heading-aware + sliding window |
| `P3-T09` Ingestion Tools Expansion | `P3-Wave3` | `DONE` | - | `ingest_url` (httpx+HTML strip+TextSplitter), `ingest_git` (shallow clone→ingest_dir→cleanup); httpx added to deps |
| `P3-T10` Repository Relationship Tracking | `P3-Wave3` | `DONE` | - | `src/minder/tools/repo_scanner.py`; walk repo, AST import extraction, service-boundary detection via pyproject.toml/package.json, idempotent upsert to KnowledgeGraphStore |
| `P3-T11` MCP Resources and Prompts | `P3-Wave4` | `DONE` | - | `src/minder/resources/__init__.py` (skills/repos/stats), `src/minder/prompts/__init__.py` (debug/review/explain/tdd_step); wired in `server.py` |
| `P3-T12` Workflow Intelligence Enhancement | `P3-Wave4` | `DONE` | - | `WorkflowPlannerNode` accepts optional `graph_store`; queries service nodes + depends_on edges; appends dependency+failing-test guidance; fully backwards-compatible |
| `P3-VERIFY` Phase 3 Acceptance Test | `P3-Wave5` | `NOT STARTED` | All waves complete | `tests/integration/test_phase3_gate.py` |

## Phase 4-5 Snapshot

| Phase | Status | Notes |
|---|---|---|
| `Phase 4` | `NOT STARTED` | Breakdown exists; no dedicated implementation wave started. |
| `Phase 5` | `NOT STARTED` | Breakdown exists; no dedicated implementation wave started. |
