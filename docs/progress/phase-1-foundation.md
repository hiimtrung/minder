# Phase 1 Tracker — Foundation

**Goal**: working MCP server baseline with auth, repo-local state, search, and delivery assets.

## Phase Status

| Area            | Status | Notes                                                       |
| --------------- | ------ | ----------------------------------------------------------- |
| Phase 1         | `DONE` | Full stack verified and closed                              |
| Acceptance gate | `DONE` | `tests/integration/test_phase1_gate.py` is the closure gate |
| Runtime posture | `DONE` | MongoDB + Redis + Milvus Standalone local baseline in place |

## Tasks

| Task        | Owner   | Wave   | Status | Summary                                                               | Related Context                                                                            |
| ----------- | ------- | ------ | ------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `P1-T01`    | `PE`    | `done` | `DONE` | Initialize Python project, lint, types, tests, base structure         | [../plan/06-operations-and-delivery.md](../plan/06-operations-and-delivery.md)             |
| `P1-T02`    | `PE`    | `done` | `DONE` | Typed config from TOML + env                                          | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                 |
| `P1-T03`    | `BE`    | `done` | `DONE` | Core models for user, skill, session, workflow, repo, history, errors | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                   |
| `P1-T04`    | `BE`    | `done` | `DONE` | MongoDB-backed operational repositories                               | [../system-design.md](../system-design.md)                                                 |
| `P1-T04A`   | `BE/PE` | `done` | `DONE` | Mongo migration/bootstrap/indexing path                               | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                   |
| `P1-T05`    | `BE`    | `done` | `DONE` | User/API key/JWT/RBAC auth layer                                      | [../system-design.md](../system-design.md)                                                 |
| `P1-T06`    | `PE`    | `1`    | `DONE` | SSE MCP transport                                                     | [../system-design.md](../system-design.md)                                                 |
| `P1-T07`    | `PE`    | `1`    | `DONE` | stdio MCP transport                                                   | [../system-design.md](../system-design.md)                                                 |
| `P1-T08`    | `BE`    | `1`    | `DONE` | JWT auth middleware for SSE                                           | [../system-design.md](../system-design.md)                                                 |
| `P1-T09`    | `ML`    | `done` | `DONE` | Local EmbeddingGemma GGUF embedding provider                          | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                 |
| `P1-T10`    | `ML`    | `done` | `DONE` | OpenAI embedding fallback                                             | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                 |
| `P1-T11`    | `ML`    | `done` | `DONE` | Milvus Standalone vector store                                        | [../system-design.md](../system-design.md)                                                 |
| `P1-T11A`   | `BE/PE` | `done` | `DONE` | Redis runtime cache/session layer                                     | [../system-design.md](../system-design.md)                                                 |
| `P1-T12`    | `BE`    | `2`    | `DONE` | `.minder/` repo-local state management                                | [../plan/04-workflow-governance.md](../plan/04-workflow-governance.md)                     |
| `P1-T13`    | `BE`    | `2`    | `DONE` | Workflow tool surface                                                 | [../plan/04-workflow-governance.md](../plan/04-workflow-governance.md)                     |
| `P1-T14`    | `BE`    | `2`    | `DONE` | Memory and semantic search tools                                      | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                   |
| `P1-T15`    | `BE`    | `2`    | `DONE` | Auth MCP tools                                                        | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                   |
| `P1-T16`    | `BE`    | `2`    | `DONE` | Session MCP tools                                                     | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                   |
| `P1-T17`    | `PE`    | `3`    | `DONE` | Initial skill seeding from external Git source                        | [../plan/01-product-scope.md](../plan/01-product-scope.md)                                 |
| `P1-T18`    | `PE`    | `done` | `DONE` | Model download script                                                 | [../guides/local-setup.md](../guides/local-setup.md)                                       |
| `P1-T19`    | `PE`    | `done` | `DONE` | Local Docker development stack                                        | [../guides/local-setup.md](../guides/local-setup.md)                                       |
| `P1-T20`    | `PE`    | `3`    | `DONE` | GitHub Actions CI                                                     | [../guides/production-deployment.md](../guides/production-deployment.md)                   |
| `P1-T21`    | `PE`    | `3`    | `DONE` | GitHub Actions release pipeline                                       | [../guides/production-deployment.md](../guides/production-deployment.md)                   |
| `P1-T22`    | `PE`    | `3`    | `DONE` | Initial admin creation script                                         | [../guides/admin-client-onboarding.md](../guides/admin-client-onboarding.md)               |
| `P1-VERIFY` | `BE/PE` | `done` | `DONE` | End-to-end Phase 1 acceptance gate                                    | [../../tests/integration/test_phase1_gate.py](../../tests/integration/test_phase1_gate.py) |
