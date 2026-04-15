# Architecture Transition Tracker — CLI Edge Extraction and Fast Graph Sync

**Goal**: replace the slow server-centric graph refresh path with a repo-local CLI extractor and a server-side graph/semantic sync architecture.

## Status

| Area               | Status      | Notes                                                                         |
| ------------------ | ----------- | ----------------------------------------------------------------------------- |
| Transition roadmap | `PROPOSED`  | Architecture direction documented; implementation not started                 |
| Review posture     | `IN REVIEW` | Core direction accepted with adjustments on embeddings and realtime transport |

## Transition Phases

| Transition Phase                     | Status    | Summary                                                                         | Related Context                                                                                                                                                                                      |
| ------------------------------------ | --------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Phase 1` Edge Node (`minder-cli`)   | `BACKLOG` | Tree-sitter extractor, delta sync, JSON payload generation, secure push API     | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md)                                                                           |
| `Phase 2` Core Infrastructure and AI | `BACKLOG` | Dual storage, orchestration flow, reasoning over graph and semantic layers      | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../system-design.md](../system-design.md)                               |
| `Phase 3` Minder MCP Server          | `BACKLOG` | MCP resources and tools over structure, TODOs, impact analysis, semantic search | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md) |
| `Phase 4` Astro Dashboard            | `BACKLOG` | Visual graph UI, branch/environment mapping, SSE-driven updates                 | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../system-design.md](../system-design.md)                               |
| `Phase 5` CI/CD and Distribution     | `BACKLOG` | PyPI release pipeline, CLI upgrade checks, deployment automation                | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../guides/production-deployment.md](../guides/production-deployment.md) |

## Key Work Items

| Work Item | Owner   | Status    | Summary                                                                      | Related Context                                                                                                                                                                                                                  |
| --------- | ------- | --------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AT-T01`  | `BE/ML` | `BACKLOG` | Define sync payload schema for files, symbols, TODOs, routes, and queue flow | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md)                                                                                                       |
| `AT-T02`  | `PE`    | `BACKLOG` | Package `minder-cli` for PyPI with parser/runtime dependencies               | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md)                                                                                                       |
| `AT-T03`  | `BE`    | `BACKLOG` | Add secure graph sync API with auth, versioning, and tenant scoping          | [../system-design.md](../system-design.md)                                                                                                                                                                                       |
| `AT-T04`  | `BE/ML` | `BACKLOG` | Replace slow GraphNode refresh with delta-based metadata ingestion           | [../design/skill_management_and_graph_metadata.md](../design/skill_management_and_graph_metadata.md); [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md) |
| `AT-T05`  | `ML`    | `BACKLOG` | Keep embeddings on a dedicated embedding model, not Gemma 4                  | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md); [../system-design.md](../system-design.md)                                                                                                             |
| `AT-T06`  | `FE`    | `BACKLOG` | Add graph visualization and environment mapping UI in the dashboard          | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md)                                                                                                       |
| `AT-T07`  | `PE`    | `BACKLOG` | GitHub Actions and PyPI trusted publishing for `minder-cli`                  | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md)                                                                                                       |
