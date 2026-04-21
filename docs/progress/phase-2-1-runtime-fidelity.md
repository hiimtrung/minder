# Phase 2.1 Tracker — Runtime Fidelity

**Goal**: replace the minimal internal runtime with the real orchestration and model runtime stack.

## Phase Status

| Area      | Status | Notes                                           |
| --------- | ------ | ----------------------------------------------- |
| Phase 2.1 | `DONE` | Runtime fidelity and fallback behavior verified |

## Tasks

| Task       | Owner | Status | Summary                          | Related Context                                                                              |
| ---------- | ----- | ------ | -------------------------------- | -------------------------------------------------------------------------------------------- |
| `P2.1-T01` | `ML`  | `DONE` | LangGraph runtime replacement    | [../plan/02-architecture.md](../plan/02-architecture.md)                                     |
| `P2.1-T02` | `ML`  | `DONE` | State contract normalization     | [../plan/02-architecture.md](../plan/02-architecture.md)                                     |
| `P2.1-T03` | `ML`  | `DONE` | Real Ollama local LLM runtime | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                   |
| `P2.1-T04` | `ML`  | `DONE` | LiteLLM OpenAI fallback          | [../plan/05-implementation-phases.md](../plan/05-implementation-phases.md)                   |
| `P2.1-T05` | `ML`  | `DONE` | LLM node fallback/error policy   | [../plan/02-architecture.md](../plan/02-architecture.md)                                     |
| `P2.1-T06` | `ML`  | `DONE` | Conditional graph routing        | [../plan/02-architecture.md](../plan/02-architecture.md)                                     |
| `P2.1-T07` | `ML`  | `DONE` | Focused runtime fidelity tests   | [../../tests/integration/test_phase2x_gate.py](../../tests/integration/test_phase2x_gate.py) |
