# Phase 3 Tracker — Retrieval, Knowledge Graph, Process Intelligence

**Goal**: improve retrieval quality and add relationship-aware repository intelligence.

## Wave Status

| Wave       | Focus                                           | Status |
| ---------- | ----------------------------------------------- | ------ |
| `P3-Wave1` | Retrieval infrastructure                        | `DONE` |
| `P3-Wave2` | Knowledge graph and extended stores             | `DONE` |
| `P3-Wave3` | Ingestion and repository relationships          | `DONE` |
| `P3-Wave4` | MCP resources/prompts and workflow intelligence | `DONE` |
| `P3-Wave5` | Acceptance gate                                 | `DONE` |

## Transition Note

This phase documents the delivered server-centric retrieval and graph baseline.

The next performance-focused replacement path for slow graph refresh lives in [architecture-transition-cli-edge-sync.md](architecture-transition-cli-edge-sync.md), where structural extraction moves to `minder-cli` and delta sync replaces broad server-side refresh as the default path.

## Tasks

| Task        | Wave       | Owner   | Status | Summary                           | Related Context                                                                                                                    |
| ----------- | ---------- | ------- | ------ | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `P3-T04`    | `P3-Wave1` | `ML`    | `DONE` | MMR diversity filtering           | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                           |
| `P3-T02`    | `P3-Wave1` | `ML`    | `DONE` | BM25 hybrid retrieval             | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                           |
| `P3-T03`    | `P3-Wave1` | `ML`    | `DONE` | Multi-hop retrieval               | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                           |
| `P3-T01`    | `P3-Wave1` | `ML`    | `DONE` | Cross-encoder reranking node      | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                           |
| `P3-T07`    | `P3-Wave1` | `ML`    | `DONE` | AST-aware code chunking           | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                           |
| `P3-T08`    | `P3-Wave1` | `ML`    | `DONE` | Text chunking                     | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                           |
| `P3-T05`    | `P3-Wave2` | `BE`    | `DONE` | Knowledge graph store             | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md); [../plan/02-architecture.md](../plan/02-architecture.md) |
| `P3-T06`    | `P3-Wave2` | `BE`    | `DONE` | Rule and feedback stores          | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                           |
| `P3-T09`    | `P3-Wave3` | `BE`    | `DONE` | URL and Git ingestion             | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                           |
| `P3-T10`    | `P3-Wave3` | `BE`    | `DONE` | Repository relationship tracking  | [../plan/02-architecture.md](../plan/02-architecture.md)                                                                           |
| `P3-T11`    | `P3-Wave4` | `BE`    | `DONE` | MCP resources and prompts         | [../plan/03-data-model-and-tools.md](../plan/03-data-model-and-tools.md)                                                           |
| `P3-T12`    | `P3-Wave4` | `BE/ML` | `DONE` | Workflow intelligence enhancement | [../plan/04-workflow-governance.md](../plan/04-workflow-governance.md)                                                             |
| `P3-VERIFY` | `P3-Wave5` | `ML/BE` | `DONE` | Phase 3 acceptance gate           | [../../tests/integration/test_phase3_gate.py](../../tests/integration/test_phase3_gate.py)                                         |
