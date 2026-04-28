# Minder — Task Breakdown

> **Document version**: 1.5 — 2026-04-15
> **Status**: ACTIVE DELIVERY BASELINE

---

## Purpose

This file is now the planning index for task breakdowns.

Detailed task tables have been split into phase-specific files under [../archive/progress/README.md](../archive/progress/README.md) so each workstream can keep its own context and related-document links without carrying the full project backlog in one document.

---

## Team Structure

| Role                         | ID   | Responsibilities                                                               |
| ---------------------------- | ---- | ------------------------------------------------------------------------------ |
| **Backend Lead**             | `BE` | Auth, data models, stores, MCP tools, workflow engine, API design              |
| **Platform Engineer**        | `PE` | Project setup, config, transport layer, Docker, CI/CD, database migrations     |
| **ML/RAG Engineer**          | `ML` | Embedding, LLM integration, LangGraph pipeline, retrieval, reranking, learning |
| **Frontend/DevOps Engineer** | `FE` | Dashboard, observability, monitoring, load testing                             |

---

## Cross-Cutting Architecture Direction

| Date       | Direction                                                                              | Source                                                                                                                                                                                                     |
| ---------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-03 | Runtime baseline is MongoDB + Redis + Milvus Standalone under Docker Compose           | [../architecture/system-design.md](../architecture/system-design.md)                                                                                                                                                                       |
| 2026-04-10 | Current non-scale Phase 4 product scope is closed; scale and hardening remain deferred | [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)                                                                                                                                                                 |
| 2026-04-15 | Skill catalog is operator-managed and graph intelligence is metadata-first             | [requirements/skill_management_and_graph_metadata.md](requirements/skill_management_and_graph_metadata.md); [../archive/features/skill_management_and_graph_metadata.md](../archive/features/skill_management_and_graph_metadata.md) |

---

## Task Trackers By Phase

| Scope              | File                                                                                                                       | Notes                                                                        |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Portfolio index    | [../archive/progress/README.md](../archive/progress/README.md)                                                                                   | Entry point for all split trackers                                           |
| Phase 1            | [../archive/progress/phase-1-foundation.md](../archive/progress/phase-1-foundation.md)                                                           | Foundation, auth, search, delivery assets                                    |
| Phase 2            | [../archive/progress/phase-2-agentic-pipeline.md](../archive/progress/phase-2-agentic-pipeline.md)                                               | Agentic pipeline core                                                        |
| Phase 2.1          | [../archive/progress/phase-2-1-runtime-fidelity.md](../archive/progress/phase-2-1-runtime-fidelity.md)                                           | Runtime fidelity and orchestration                                           |
| Phase 2.2          | [../archive/progress/phase-2-2-verification-and-retrieval.md](../archive/progress/phase-2-2-verification-and-retrieval.md)                       | Retrieval, verification, workflow closure                                    |
| Phase 3            | [../archive/progress/phase-3-retrieval-and-graph.md](../archive/progress/phase-3-retrieval-and-graph.md)                                         | Retrieval quality, graph, ingestion                                          |
| Phase 4 overview   | [../archive/progress/phase-4-overview.md](../archive/progress/phase-4-overview.md)                                                               | Shared Phase 4 tasks and posture                                             |
| Phase 4.0          | [../archive/progress/phase-4-0-gateway-auth-and-dashboard-foundation.md](../archive/progress/phase-4-0-gateway-auth-and-dashboard-foundation.md) | Gateway auth + dashboard foundation                                          |
| Phase 4.1          | [../archive/progress/phase-4-1-setup-and-plug-and-play-auth.md](../archive/progress/phase-4-1-setup-and-plug-and-play-auth.md)                   | Setup and direct auth                                                        |
| Phase 4.2          | [../archive/progress/phase-4-2-client-management-dashboard.md](../archive/progress/phase-4-2-client-management-dashboard.md)                     | Client management UX                                                         |
| Phase 4.3          | [../archive/progress/phase-4-3-console-clean-architecture.md](../archive/progress/phase-4-3-console-clean-architecture.md)                       | Clean architecture + Astro migration                                         |
| Phase 4.4          | [../archive/progress/phase-4-4-context-continuity.md](../archive/progress/phase-4-4-context-continuity.md)                                       | Context continuity backlog                                                   |
| Phase 5            | [../progress/phase-5-learning-and-skill-catalog.md](../progress/phase-5-learning-and-skill-catalog.md)                           | Learning, skill catalog, metadata-first graph, dashboard local chat          |
| Phase 6            | [../archive/progress/phase-6-branch-topology-automation.md](../archive/progress/phase-6-branch-topology-automation.md)                           | Post-Phase-5 branch topology, repo-local IDE bootstrap, installer automation |
| Transition roadmap | [../archive/progress/architecture-transition-cli-edge-sync.md](../archive/progress/architecture-transition-cli-edge-sync.md)                     | New CLI edge extraction and graph sync modernization track                   |

---

## Global Planning Context

| Topic                                 | File                                                                                                                 |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| System design                         | [../architecture/system-design.md](../architecture/system-design.md)                                                                                 |
| Product scope                         | [./01-product-scope.md](./01-product-scope.md)                                                                 |
| Architecture planning notes           | [./02-architecture.md](./02-architecture.md)                                                                   |
| Data model and MCP surface            | [./03-data-model-and-tools.md](./03-data-model-and-tools.md)                                                   |
| Workflow governance                   | [./04-workflow-governance.md](./04-workflow-governance.md)                                                     |
| Phase sequencing                      | [./05-implementation-phases.md](./05-implementation-phases.md)                                                 |
| CLI edge extraction transition design | [../archive/features/cli_edge_extractor_and_graph_sync_architecture.md](../archive/features/cli_edge_extractor_and_graph_sync_architecture.md) |
