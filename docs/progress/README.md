# Minder Progress Index

**Date**: 2026-04-16
**Purpose**: split task and progress tracking by phase and phase-part so each tracker keeps only the context it needs.

---

## How To Use This Folder

- Use the phase file that matches the workstream you are touching.
- Each file keeps both task breakdown and progress status in table form.
- Every task row links to the most relevant design, requirements, architecture, or test context.
- [../roadmap/PROJECT_PROGRESS.md](../roadmap/PROJECT_PROGRESS.md) is now the portfolio-level overview only.
- [../roadmap/TASK_BREAKDOWN.md](../roadmap/TASK_BREAKDOWN.md) is now the planning index only.

---

## Tracker Files

| File                                                                                                     | Scope                                                                                        | Status                             |
| -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------- |
| [../archive/progress/phase-1-foundation.md](../archive/progress/phase-1-foundation.md)                                                           | Phase 1 foundation, auth, transport, search, CI/CD                                           | Closed                             |
| [../archive/progress/phase-2-agentic-pipeline.md](../archive/progress/phase-2-agentic-pipeline.md)                                               | Phase 2 core agentic pipeline                                                                | Closed                             |
| [../archive/progress/phase-2-1-runtime-fidelity.md](../archive/progress/phase-2-1-runtime-fidelity.md)                                           | Phase 2.1 runtime fidelity and orchestration replacement                                     | Closed                             |
| [../archive/progress/phase-2-2-verification-and-retrieval.md](../archive/progress/phase-2-2-verification-and-retrieval.md)                       | Phase 2.2 verification, retrieval, workflow closure                                          | Closed                             |
| [../archive/progress/phase-3-retrieval-and-graph.md](../archive/progress/phase-3-retrieval-and-graph.md)                                         | Phase 3 retrieval, knowledge graph, ingestion, workflow intelligence                         | Closed                             |
| [../archive/progress/phase-4-overview.md](../archive/progress/phase-4-overview.md)                                                               | Phase 4 portfolio posture and shared Phase 4 tasks                                           | Closed for delivered product slice |
| [../archive/progress/phase-4-0-gateway-auth-and-dashboard-foundation.md](../archive/progress/phase-4-0-gateway-auth-and-dashboard-foundation.md) | Phase 4.0 gateway auth and dashboard foundation                                              | Closed                             |
| [../archive/progress/phase-4-1-setup-and-plug-and-play-auth.md](../archive/progress/phase-4-1-setup-and-plug-and-play-auth.md)                   | Phase 4.1 setup and direct client auth                                                       | Closed                             |
| [../archive/progress/phase-4-2-client-management-dashboard.md](../archive/progress/phase-4-2-client-management-dashboard.md)                     | Phase 4.2 client management dashboard UX                                                     | Closed                             |
| [../archive/progress/phase-4-3-console-clean-architecture.md](../archive/progress/phase-4-3-console-clean-architecture.md)                       | Phase 4.3 clean architecture and Astro console migration                                     | Closed                             |
| [../archive/progress/phase-4-4-context-continuity.md](../archive/progress/phase-4-4-context-continuity.md)                                       | Phase 4.4 context continuity and anti-drift backlog                                          | Backlog                            |
| [phase-5-learning-and-skill-catalog.md](phase-5-learning-and-skill-catalog.md)                           | Phase 5 delivered learning, skill catalog, metadata-first graph, and dashboard runtime slice | Closed                             |
| [../archive/progress/phase-6-branch-topology-automation.md](../archive/progress/phase-6-branch-topology-automation.md)                           | Phase 6 CLI completion, repo-local IDE bootstrap, and first-release preparation              | Closed                             |
| [phase-7-learning-and-advanced-runtime.md](phase-7-learning-and-advanced-runtime.md)                     | Phase 7 deferred learning backlog, advanced runtime UX, and post-CLI reconciliation          | Planned                            |
| [../archive/progress/architecture-transition-cli-edge-sync.md](../archive/progress/architecture-transition-cli-edge-sync.md)                     | New transition roadmap for CLI edge extraction and fast graph sync                           | Closed for current scope           |

---

## Global Context

| Context                                            | File                                                                                                                       |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| System-level runtime and architecture              | [../architecture/system-design.md](../architecture/system-design.md)                                                                                 |
| Product scope                                      | [../roadmap/01-product-scope.md](../roadmap/01-product-scope.md)                                                                 |
| Planning architecture notes                        | [../architecture/architecture-vision.md](../architecture/architecture-vision.md)                                                                   |
| Data model and MCP surface                         | [../roadmap/03-data-model-and-tools.md](../roadmap/03-data-model-and-tools.md)                                                   |
| Phase sequencing                                   | [../roadmap/05-implementation-phases.md](../roadmap/05-implementation-phases.md)                                                 |
| Skill catalog and metadata-only graph features     | [../features/skill-management.md](../features/skill-management.md)           |
| CLI edge extractor and sync design                 | [../archive/features/cli_edge_extractor_and_graph_sync_architecture.md](../archive/features/cli_edge_extractor_and_graph_sync_architecture.md) |
