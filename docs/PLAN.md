# Minder Plan Index

This document is the entry point for the Minder implementation plan. The full plan has been split into smaller files so it is easier to review, maintain, and update.

## Canonical Architecture Reference

Use [System Design](../docs/system-design.md) as the system-level source of truth.

Use this `PLAN` index and the `docs/plan/*` files for:

- phased planning
- delivery sequence
- implementation scope
- operational rollout details

## Planning Documents

1. [01-product-scope.md](./plan/01-product-scope.md)
2. [02-architecture.md](./plan/02-architecture.md)
3. [03-data-model-and-tools.md](./plan/03-data-model-and-tools.md)
4. [04-workflow-governance.md](./plan/04-workflow-governance.md)
5. [05-implementation-phases.md](./plan/05-implementation-phases.md)
6. [06-operations-and-delivery.md](./plan/06-operations-and-delivery.md)

## Current Baseline Decisions

| Topic                  | Decision                                            |
| ---------------------- | --------------------------------------------------- |
| Target users           | Team, shared server, multi-user                     |
| Authentication         | API key plus JWT with RBAC                          |
| Transport              | SSE from Phase 1, stdio for local dev               |
| Local embedding model  | `ggml-org/embeddinggemma-300M-GGUF` quantized GGUF  |
| Local LLM              | `ggml-org/gemma-4-E2B-it-GGUF` quantized GGUF       |
| Runtime                | `llama.cpp` via `llama-cpp-python`                  |
| Verification           | Docker sandbox in production                        |
| Workflow governance    | Required                                            |
| Repository-local state | Required under `.minder/`                           |
| Dashboard              | Required                                            |
| CI/CD                  | GitHub Actions, Releases, and Packages from Phase 1 |

## Current Delivery Focus — 2026-04-09

### Completed baseline

- Foundation, pipeline, and advanced retrieval phases are complete.
- Dashboard foundation through client-management parity is complete (P4.3 DONE).
- Rate limiting is complete.
- Post-P4.3 dashboard routing refinements are in progress:
  - New `ClientConsoleShell` component extracted for clients registry page.
  - No-op `middleware.ts` added to prevent `[clientId]` route-rewriting regression.
  - Client routing and detail management refactored (commits since P4.3 closure).

### Active next steps

1. **Commit** the in-progress dashboard routing polish (`ClientConsoleShell.astro`, `middleware.ts`, updated `clients/index.astro`).
2. **Build the observability foundation** (`P4-T05`): `src/minder/observability/` is a confirmed-empty placeholder — implement OpenTelemetry tracing, Prometheus `/metrics`, structured JSON logging, and durable audit instrumentation.
3. **Expand the admin/dashboard surface** for workflow, repository, and user administration (`P4-T07`, `P4-T08`, `P4-T09`).
4. Follow with a focused security and operability hardening pass (`P4-T12`).

### Explicitly deferred for now

- MongoDB production topology upgrade.
- Milvus cluster-ready deployment.
- Redis HA and failover work.
- Production-scale Compose hardening.
- Formal load testing for scale-up readiness.

For status tracking, use [docs/PROJECT_PROGRESS.md](./PROJECT_PROGRESS.md). For the full task catalog, use [docs/TASK_BREAKDOWN.md](./TASK_BREAKDOWN.md).

## Recommended Reading Order

1. Start with product scope and goals.
2. Review [System Design](../docs/system-design.md) for runtime architecture and system boundaries.
3. Review data stores, MCP tools, and configuration.
4. Review workflow governance and repository-local state.
5. Review phased implementation.
6. Review operational concerns, risks, CI/CD, and metrics.

_Document version: 4.2 - Updated: 2026-04-09_
_Status: ACTIVE DELIVERY BASELINE_
