# Minder — Project Progress

> **Purpose**: single control board for tracking delivery progress across the whole project
> **Last updated**: 2026-04-03

---

## Project Overview

| Phase | Goal | Status | Current wave | Main blocker | Notes |
|---|---|---|---|---|---|
| `Phase 1` | Foundation: MCP server, auth, search, CI/CD | `IN PROGRESS` | `architecture reset queued` | Stack target changed to MongoDB + Redis + Milvus Standalone in Docker Compose | Earlier Waves 1-4 remain useful, but storage/deployment sign-off must be reworked. |
| `Phase 2` | Agentic pipeline: reasoning, retrieval, verification | `FUNCTIONALLY COMPLETE` | `closed baseline` | Runtime fidelity and deployment environment | Minimal end-to-end path is implemented and tested. |
| `Phase 2.1` | Runtime fidelity and orchestration replacement | `PARTIAL` | `baseline complete` | Real LangGraph + llama_cpp + LiteLLM environment | Optional real runtime paths exist; environment is not fully provisioned. |
| `Phase 2.2` | Verification, retrieval, and workflow closure | `PARTIAL` | `baseline complete` | Production-grade Docker/runtime packaging | Retrieval, repo ingest, and verification contracts exist. |
| `Phase 3` | Advanced retrieval, knowledge graph, process intelligence | `NOT STARTED` | `backlog` | Depends on Phase 2.x sign-off | No dedicated implementation wave has started. |
| `Phase 4` | Production scale, multi-user, dashboard | `NOT STARTED` | `backlog` | Depends on Phase 3 and production deployment choices | Planning exists only in breakdown docs. |
| `Phase 5` | Learning and self-improvement | `NOT STARTED` | `backlog` | Depends on reliable history/feedback foundation | Planning exists only in breakdown docs. |

---

## Phase 1 Tracker

| Task | Owner | Wave | Status | Blocker | Last update |
|---|---|---|---|---|---|
| `P1-T01` Project Initialization | `PE` | `done` | `DONE` | `-` | `Python 3.14 baseline verified` |
| `P1-T02` Configuration System | `PE` | `done` | `DONE` | `-` | `Config tests passing` |
| `P1-T03` Data Models | `BE` | `done` | `DONE` | `-` | `Model coverage in place` |
| `P1-T04` Primary Operational Store (MongoDB) | `BE` | `Wave 5` | `PARTIAL` | `Current implementation is still SQLite-backed` | `Target changed from SQLite to MongoDB` |
| `P1-T04A` MongoDB Repository Migration | `BE/PE` | `Wave 5` | `NOT STARTED` | `Needs schema/index/config/migration design` | `New task added for architecture reset` |
| `P1-T05` Auth Layer | `BE` | `done` | `DONE` | `-` | `JWT/RBAC/API key flow implemented` |
| `P1-T06` SSE Transport | `1` | `PARTIAL` | `Actual SSE server lifecycle/network listener still missing` | `Wave 1 transport facade + tests committed` |
| `P1-T07` Stdio Transport | `1` | `PARTIAL` | `Real stdio server lifecycle still missing` | `Wave 1 transport facade + tests committed` |
| `P1-T08` Auth Middleware for SSE | `1` | `PARTIAL` | `Not yet bound to real SSE connection/session lifecycle` | `Dispatch-path auth integration completed` |
| `P1-T09` Embedding Layer (Qwen GGUF) | `backlog` | `PARTIAL` | `Model provisioning/runtime environment not closed` | `Optional llama_cpp path exists` |
| `P1-T10` Embedding Fallback (OpenAI) | `done` | `DONE` | `-` | `Fallback provider exists` |
| `P1-T11` Vector Store (Milvus Standalone) | `Wave 6` | `PARTIAL` | `Current substrate is not connected to Milvus Standalone` | `Target changed from Milvus Lite/local path to Milvus Standalone` |
| `P1-T11A` Redis Runtime Layer | `Wave 5` | `NOT STARTED` | `No Redis-backed cache/session/runtime layer yet` | `New task added for architecture reset` |
| `P1-T12` Repository-Local State Management | `2` | `DONE` | `-` | `Wave 2 repo-state store + integration test completed` |
| `P1-T13` Workflow Engine (Basic) | `2` | `PARTIAL` | `Real SSE/stdio round-trip coverage still missing` | `Workflow tool module + server registration completed` |
| `P1-T14` Memory & Search Tools (Basic) | `2` | `DONE` | `-` | `Memory/search modules + integration test completed` |
| `P1-T15` Auth MCP Tools | `2` | `PARTIAL` | `Real SSE/stdio round-trip coverage still missing` | `Auth tool module + server registration completed` |
| `P1-T16` Session Tools | `2` | `PARTIAL` | `Real SSE/stdio round-trip coverage still missing` | `Session tool module + server registration completed` |
| `P1-T17` Skill Seeding | `3` | `PARTIAL` | `Git clone path not exercised against a real remote in tests` | `Local seeding + idempotence contract implemented` |
| `P1-T18` Model Download Script | `3` | `PARTIAL` | `Download script not executed in CI/local verification yet` | `Skip/checksum contract implemented` |
| `P1-T19` Docker Development Stack | `Wave 6` | `PARTIAL` | `Compose must expand from app-only to app + MongoDB + Redis + Milvus` | `Dockerfile, compose, and server entrypoint added` |
| `P1-T20` GitHub Actions CI | `3` | `PARTIAL` | `Workflow file created but not exercised on GitHub yet` | `ci.yml added with lint/type/test/docker steps` |
| `P1-T21` GitHub Actions Release | `3` | `PARTIAL` | `Workflow file created but not exercised on a real tag yet` | `release.yml added for ghcr + GitHub Release` |
| `P1-T22` Admin Creation Script | `3` | `DONE` | `-` | `Idempotent create_admin contract implemented and tested` |
| `P1-VERIFY` Phase 1 Acceptance Test | `Wave 7` | `PARTIAL` | `Gate must be re-baselined for MongoDB + Redis + Milvus Standalone` | `Local phase1 gate exists but no longer matches final infra target` |

## Architecture Reset — 2026-04-03

| Area | Current baseline | Target before Phase 3 | Tracking implication |
|---|---|---|---|
| Operational store | `SQLite` | `MongoDB` | Re-open `P1-T04` and add `P1-T04A` migration task |
| Runtime cache/session | `In-process / partial` | `Redis` | Add `P1-T11A` and wire Compose/runtime config |
| Vector store deployment | `Local substrate / Milvus Lite assumption` | `Milvus Standalone` | Re-scope `P1-T11` and `P1-T19` |
| Local deployment shape | `App container mainly` | `Compose-managed multi-service stack` | Re-scope `P1-T19` and `P1-VERIFY` |

## Recommended Next Waves

| Wave | Focus | Tasks |
|---|---|---|
| `Wave 5` | Operational persistence reset | `P1-T04`, `P1-T04A`, `P1-T11A` |
| `Wave 6` | Vector/deployment packaging | `P1-T11`, `P1-T19`, `P1-T18` |
| `Wave 7` | Acceptance re-baseline | `P1-VERIFY`, `P1-T20`, `P1-T21` |

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
| LangGraph adapter path | `PARTIAL` | Optional adapter exists; full runtime depends on installed dependency. |
| llama_cpp local runtime | `PARTIAL` | Optional real path exists; active environment may still run mock path. |
| LiteLLM fallback path | `PARTIAL` | Optional real path exists; active environment may still run mock path. |
| Repo ingest + retrieval substrate | `DONE` | Ingest and vector-backed retrieval are implemented. |
| Verification contract | `DONE` | Docker/subprocess contract and failure classification are implemented. |
| Phase 2.x gate | `DONE` | `tests/integration/test_phase2x_gate.py` passes. |

## Phase 3-5 Snapshot

| Phase | Status | Notes |
|---|---|---|
| `Phase 3` | `NOT STARTED` | Breakdown exists; no dedicated implementation wave started. |
| `Phase 4` | `NOT STARTED` | Breakdown exists; no dedicated implementation wave started. |
| `Phase 5` | `NOT STARTED` | Breakdown exists; no dedicated implementation wave started. |
