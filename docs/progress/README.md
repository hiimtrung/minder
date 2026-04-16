# Minder Progress Index

**Date**: 2026-04-16
**Purpose**: split task and progress tracking by phase and phase-part so each tracker keeps only the context it needs.

---

## How To Use This Folder

- Use the phase file that matches the workstream you are touching.
- Each file keeps both task breakdown and progress status in table form.
- Every task row links to the most relevant design, requirements, architecture, or test context.
- [../PROJECT_PROGRESS.md](../PROJECT_PROGRESS.md) is now the portfolio-level overview only.
- [../TASK_BREAKDOWN.md](../TASK_BREAKDOWN.md) is now the planning index only.

---

## Tracker Files

| File                                                                                                     | Scope                                                                | Status                             |
| -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------- |
| [phase-1-foundation.md](phase-1-foundation.md)                                                           | Phase 1 foundation, auth, transport, search, CI/CD                   | Closed                             |
| [phase-2-agentic-pipeline.md](phase-2-agentic-pipeline.md)                                               | Phase 2 core agentic pipeline                                        | Closed                             |
| [phase-2-1-runtime-fidelity.md](phase-2-1-runtime-fidelity.md)                                           | Phase 2.1 runtime fidelity and orchestration replacement             | Closed                             |
| [phase-2-2-verification-and-retrieval.md](phase-2-2-verification-and-retrieval.md)                       | Phase 2.2 verification, retrieval, workflow closure                  | Closed                             |
| [phase-3-retrieval-and-graph.md](phase-3-retrieval-and-graph.md)                                         | Phase 3 retrieval, knowledge graph, ingestion, workflow intelligence | Closed                             |
| [phase-4-overview.md](phase-4-overview.md)                                                               | Phase 4 portfolio posture and shared Phase 4 tasks                   | Closed for delivered product slice |
| [phase-4-0-gateway-auth-and-dashboard-foundation.md](phase-4-0-gateway-auth-and-dashboard-foundation.md) | Phase 4.0 gateway auth and dashboard foundation                      | Closed                             |
| [phase-4-1-setup-and-plug-and-play-auth.md](phase-4-1-setup-and-plug-and-play-auth.md)                   | Phase 4.1 setup and direct client auth                               | Closed                             |
| [phase-4-2-client-management-dashboard.md](phase-4-2-client-management-dashboard.md)                     | Phase 4.2 client management dashboard UX                             | Closed                             |
| [phase-4-3-console-clean-architecture.md](phase-4-3-console-clean-architecture.md)                       | Phase 4.3 clean architecture and Astro console migration             | Closed                             |
| [phase-4-4-context-continuity.md](phase-4-4-context-continuity.md)                                       | Phase 4.4 context continuity and anti-drift backlog                  | Backlog                            |
| [phase-5-learning-and-skill-catalog.md](phase-5-learning-and-skill-catalog.md)                           | Phase 5 learning, skill catalog, metadata-first graph backlog        | Backlog                            |
| [phase-6-branch-topology-automation.md](phase-6-branch-topology-automation.md)                           | Phase 6 post-Phase-5 CLI branch-topology automation backlog          | Backlog                            |
| [architecture-transition-cli-edge-sync.md](architecture-transition-cli-edge-sync.md)                     | New transition roadmap for CLI edge extraction and fast graph sync   | Closed for current scope           |

---

## Global Context

| Context                                            | File                                                                                                                       |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| System-level runtime and architecture              | [../system-design.md](../system-design.md)                                                                                 |
| Product scope                                      | [../plan/01-product-scope.md](../plan/01-product-scope.md)                                                                 |
| Planning architecture notes                        | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                   |
| Data model and MCP surface                         | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                   |
| Phase sequencing                                   | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                 |
| Skill catalog and metadata-only graph requirements | [../requirements/skill_management_and_graph_metadata.md](../requirements/skill_management_and_graph_metadata.md)           |
| Skill catalog and metadata-only graph design       | [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md)                       |
| CLI edge extractor and sync design                 | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md) |
