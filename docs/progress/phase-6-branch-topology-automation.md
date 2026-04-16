# Phase 6 Tracker — Branch Topology Automation

**Goal**: move CLI-side branch-topology discovery into a dedicated post-Phase-5 track so Minder can infer and submit `branch_relationships` without diluting the current transition focus on cross-repo impact traversal.

## Status

| Area    | Status        | Notes                                                         |
| ------- | ------------- | ------------------------------------------------------------- |
| Phase 6 | `NOT STARTED` | Queued after `Phase 5`; intentionally separated from `AT-T11` |

## Scope Note

This phase carries forward the old transition backlog item `AT-T10`.

The transition tracker has already closed runtime search, impact, and prompt-context follow-up in `AT-T11`, while this phase owns the remaining CLI/repo-scanner automation for discovering and submitting branch topology.

## Tasks

| Task        | Owner   | Status        | Summary                                                                                                                                             | Related Context                                                                                                                                                                                                            |
| ----------- | ------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P6-T01`    | `PE/BE` | `NOT STARTED` | Extend `minder-cli` and the repo scanner so sync can auto-detect and submit `branch_relationships` from local branch, remotes, and worktree context | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../guides/minder-cli.md](../guides/minder-cli.md); [../system-design.md](../system-design.md) |
| `P6-T02`    | `BE`    | `NOT STARTED` | Reconcile inferred branch topology with persisted repository-landscape links and preserve safe fallback to admin-managed overrides                  | [architecture-transition-cli-edge-sync.md](architecture-transition-cli-edge-sync.md); [../system-design.md](../system-design.md)                                                                                           |
| `P6-VERIFY` | `PE/BE` | `NOT STARTED` | Phase 6 acceptance gate                                                                                                                             | [../design/cli_edge_extractor_and_graph_sync_architecture.md](../design/cli_edge_extractor_and_graph_sync_architecture.md); [../guides/minder-cli.md](../guides/minder-cli.md)                                             |
