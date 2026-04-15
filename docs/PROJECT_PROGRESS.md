# Minder — Project Progress

> **Purpose**: portfolio-level control board for phase status only
> **Last updated**: 2026-04-15

---

## Overview

Detailed tracker tables now live in [progress/README.md](progress/README.md).

Use this file to understand overall phase posture, not to manage per-task details.

---

## Project Overview

| Phase        | Goal                                                      | Status        | Current wave        | Main blocker                                           | Detailed tracker                                                                                       |
| ------------ | --------------------------------------------------------- | ------------- | ------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `Phase 1`    | Foundation: MCP server, auth, search, CI/CD               | `DONE`        | `foundation closed` | `-`                                                    | [progress/phase-1-foundation.md](progress/phase-1-foundation.md)                                       |
| `Phase 2`    | Agentic pipeline: reasoning, retrieval, verification      | `DONE`        | `pipeline closed`   | `-`                                                    | [progress/phase-2-agentic-pipeline.md](progress/phase-2-agentic-pipeline.md)                           |
| `Phase 2.1`  | Runtime fidelity and orchestration replacement            | `DONE`        | `closed`            | `-`                                                    | [progress/phase-2-1-runtime-fidelity.md](progress/phase-2-1-runtime-fidelity.md)                       |
| `Phase 2.2`  | Verification, retrieval, workflow closure                 | `DONE`        | `closed`            | `-`                                                    | [progress/phase-2-2-verification-and-retrieval.md](progress/phase-2-2-verification-and-retrieval.md)   |
| `Phase 3`    | Advanced retrieval, knowledge graph, process intelligence | `DONE`        | `closed`            | `-`                                                    | [progress/phase-3-retrieval-and-graph.md](progress/phase-3-retrieval-and-graph.md)                     |
| `Phase 4`    | Production scale, multi-user, dashboard                   | `DONE`        | `closed`            | `-`                                                    | [progress/phase-4-overview.md](progress/phase-4-overview.md)                                           |
| `Phase 5`    | Learning and self-improvement                             | `NOT STARTED` | `backlog`           | `Depends on reliable history/feedback foundation`      | [progress/phase-5-learning-and-skill-catalog.md](progress/phase-5-learning-and-skill-catalog.md)       |
| `Transition` | CLI edge extraction and fast graph sync                   | `PROPOSED`    | `review`            | `Needs roadmap approval and implementation sequencing` | [progress/architecture-transition-cli-edge-sync.md](progress/architecture-transition-cli-edge-sync.md) |

---

## Current Delivery Stance

| Category                | Current Decision                    | Notes                                                                                               |
| ----------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| Active product work     | `Phase 4 delivered slice is closed` | `P4.0` through `P4.3` plus shared `P4-T04` to `P4-T10` are complete                                 |
| Deferred infrastructure | `Cluster/HA/scale-up work deferred` | `P4-T01`, `P4-T02`, `P4-T03`, `P4-T11`, `P4-T12`, `P4-VERIFY` remain backlog                        |
| Planning focus          | `Phase 5 backlog remains open`      | Includes skill catalog CRUD/import and metadata-first graph refinement                              |
| Architecture transition | `CLI edge sync under review`        | Introduces `minder-cli`, secure metadata sync, and a faster replacement path for slow graph refresh |

---

## Recommended Next Tracking Files

| If you are working on...                           | Open this tracker                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent runtime and retrieval core                   | [progress/phase-2-agentic-pipeline.md](progress/phase-2-agentic-pipeline.md)                                                                                                                                                                                                                                                                                                                                                                       |
| Runtime fidelity or verification contracts         | [progress/phase-2-1-runtime-fidelity.md](progress/phase-2-1-runtime-fidelity.md), [progress/phase-2-2-verification-and-retrieval.md](progress/phase-2-2-verification-and-retrieval.md)                                                                                                                                                                                                                                                             |
| Retrieval, graph, ingestion, workflow intelligence | [progress/phase-3-retrieval-and-graph.md](progress/phase-3-retrieval-and-graph.md)                                                                                                                                                                                                                                                                                                                                                                 |
| CLI edge extraction transition                     | [progress/architecture-transition-cli-edge-sync.md](progress/architecture-transition-cli-edge-sync.md)                                                                                                                                                                                                                                                                                                                                             |
| Shared Phase 4 posture or deferred infra           | [progress/phase-4-overview.md](progress/phase-4-overview.md)                                                                                                                                                                                                                                                                                                                                                                                       |
| Dashboard/auth client-management history           | [progress/phase-4-0-gateway-auth-and-dashboard-foundation.md](progress/phase-4-0-gateway-auth-and-dashboard-foundation.md), [progress/phase-4-1-setup-and-plug-and-play-auth.md](progress/phase-4-1-setup-and-plug-and-play-auth.md), [progress/phase-4-2-client-management-dashboard.md](progress/phase-4-2-client-management-dashboard.md), [progress/phase-4-3-console-clean-architecture.md](progress/phase-4-3-console-clean-architecture.md) |
| Context continuity backlog                         | [progress/phase-4-4-context-continuity.md](progress/phase-4-4-context-continuity.md)                                                                                                                                                                                                                                                                                                                                                               |
| Learning, skill catalog, metadata-only graph       | [progress/phase-5-learning-and-skill-catalog.md](progress/phase-5-learning-and-skill-catalog.md)                                                                                                                                                                                                                                                                                                                                                   |
