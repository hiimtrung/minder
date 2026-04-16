# Phase 5 Tracker — Learning, Skill Catalog, Metadata-Only Graph

**Goal**: let Minder learn from workflows and expose a first-class skill catalog while keeping graph intelligence metadata-first.

## Status

| Area                      | Status        | Notes                                                                   |
| ------------------------- | ------------- | ----------------------------------------------------------------------- |
| Phase 5                   | `NOT STARTED` | Backlog only                                                            |
| Skill catalog expansion   | `BACKLOG`     | Dashboard CRUD and provider-agnostic import planned                     |
| Graph metadata refinement | `BACKLOG`     | Metadata-only `GraphNode` policy documented, not implemented end-to-end |

## Transition Note

The metadata-only graph backlog in this phase now has a related transition track: [architecture-transition-cli-edge-sync.md](architecture-transition-cli-edge-sync.md).

That transition plan adds a standalone `minder-cli` extractor and secure sync path so the server no longer has to perform the slow graph refresh workflow by default.

CLI-side automatic `branch_relationships` discovery is intentionally tracked separately in a post-Phase-5 file, [phase-6-branch-topology-automation.md](phase-6-branch-topology-automation.md), so Phase 5 stays focused on learning, skill synthesis, and metadata-first graph refinement.

## Tasks

| Task        | Owner   | Status    | Summary                                                    | Related Context                                                                                                                                                                                                        |
| ----------- | ------- | --------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P5-T01`    | `ML`    | `BACKLOG` | Pattern extractor from successful workflows                | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                                                                                                             |
| `P5-T02`    | `ML`    | `BACKLOG` | Skill synthesizer                                          | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                                                                                                             |
| `P5-T03`    | `ML`    | `BACKLOG` | Error learner                                              | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                                                                                                             |
| `P5-T04`    | `ML`    | `BACKLOG` | Quality optimizer                                          | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                                                                                                             |
| `P5-T05`    | `ML`    | `BACKLOG` | Reflection node                                            | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                                                                                                                                             |
| `P5-T06`    | `BE`    | `BACKLOG` | Memory compaction MCP tool                                 | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                                                                                                               |
| `P5-T07`    | `BE`    | `BACKLOG` | Skill MCP tools with workflow-step and provenance metadata | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md); [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md)                                         |
| `P5-T07A`   | `FE/BE` | `BACKLOG` | Dashboard skill catalog CRUD                               | [../requirements/skill_management_and_graph_metadata.md](../requirements/skill_management_and_graph_metadata.md); [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md) |
| `P5-T07B`   | `BE/PE` | `BACKLOG` | Remote skill import from GitHub, GitLab, generic Git       | [../requirements/skill_management_and_graph_metadata.md](../requirements/skill_management_and_graph_metadata.md); [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md) |
| `P5-T08`    | `BE`    | `PARTIAL` | Ingestion MCP tool registration                            | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                                                                                                               |
| `P5-T08A`   | `ML/BE` | `BACKLOG` | Metadata-only graph extraction policy                      | [../requirements/skill_management_and_graph_metadata.md](../requirements/skill_management_and_graph_metadata.md); [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md) |
| `P5-T09`    | `BE`    | `BACKLOG` | Admin runtime tools                                        | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                                                                                                               |
| `P5-T10`    | `BE`    | `BACKLOG` | Session expiry and cleanup                                 | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                                                                                                               |
| `P5-VERIFY` | `ML/BE` | `BACKLOG` | Phase 5 acceptance gate                                    | [../requirements/skill_management_and_graph_metadata.md](../requirements/skill_management_and_graph_metadata.md); [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md) |
