# Minder Plan Index

This document is the entry point for the Minder implementation plan. The full plan has been split into smaller files so it is easier to review, maintain, and update.

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
| Local embedding model  | `Qwen/Qwen3-Embedding-0.6B` quantized GGUF          |
| Local LLM              | `Qwen3.5-0.8B` quantized GGUF                       |
| Runtime                | `llama.cpp` via `llama-cpp-python`                  |
| Verification           | Docker sandbox in production                        |
| Workflow governance    | Required                                            |
| Repository-local state | Required under `.minder/`                           |
| Dashboard              | Required                                            |
| CI/CD                  | GitHub Actions, Releases, and Packages from Phase 1 |

## Recommended Reading Order

1. Start with product scope and goals.
2. Review the architecture and system boundaries.
3. Review data stores, MCP tools, and configuration.
4. Review workflow governance and repository-local state.
5. Review phased implementation.
6. Review operational concerns, risks, CI/CD, and metrics.

_Document version: 4.0 - Updated: 2026-04-01_
_Status: READY FOR IMPLEMENTATION REVIEW_
