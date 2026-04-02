# Phase 2 Manual Test Guide

This guide is the manual verification path for the implemented Phase 2 and Phase 2.x baseline before starting Phase 3.

## Current Status

The codebase now includes:

- Phase 2 graph state, nodes, query/search tools, history/error stores, workflow-aware prompting, guard, evaluator, and verification
- Phase 2.x runtime fidelity layers for optional `LangGraph`, `llama_cpp`, and `LiteLLM`
- Phase 2.x retrieval substrate with repo ingestion, document store, vector search, and code search alignment
- Hardened verification result contracts and Docker failure classification

What is **not** currently provisioned on this machine by default:

- `langgraph`
- `llama_cpp`
- `litellm`
- local GGUF model files under `~/.minder/models`
- Docker image `minder-sandbox:latest`

So there are two manual test modes:

1. `Baseline Mode`: verify the full flow with the repo's built-in mock/optional fallbacks
2. `Runtime Mode`: verify the same flow using installed optional runtimes

## 1. Baseline Mode

This confirms that the whole Phase 2/2.x pipeline works end-to-end in the current repo state.

### 1.1 Quality Gate

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run ruff check .
UV_CACHE_DIR=.uv-cache uv run mypy src
UV_CACHE_DIR=.uv-cache uv run pytest
```

Expected:

- `ruff` passes
- `mypy` passes
- all tests pass

### 1.2 End-to-End Smoke Run

Run:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/phase2_manual_smoke.py
```

Expected:

- query result includes `provider`, `runtime`, `verification_result`, `workflow`, and `transition_log`
- code search returns at least one code hit
- error search returns a hit after the forced retry/failure path
- workflow moves from `Test Writing` to `Implementation`

## 2. Runtime Mode

This verifies the optional real runtime paths.

### 2.1 Install Optional Dependencies

Recommended:

```bash
UV_CACHE_DIR=.uv-cache uv add langgraph litellm llama-cpp-python
```

If `llama-cpp-python` fails to compile on your machine, treat that as an environment issue, not a repo logic issue.

### 2.2 Prepare Model Files

Create the model directory:

```bash
mkdir -p ~/.minder/models
```

Place these files there:

- one GGUF embedding model for `Qwen/Qwen3-Embedding-0.6B`
- one GGUF local LLM for `Qwen3.5-0.8B`

They must match the paths configured in [`minder.toml`](/Users/trungtran/ai-agents/minder/minder.toml).

### 2.3 Build the Docker Sandbox Image

From repo root:

```bash
docker build -t minder-sandbox:latest -f docker/Dockerfile.sandbox .
```

Check:

```bash
docker image inspect minder-sandbox:latest
```

Expected:

- the image exists
- inspect returns JSON instead of `No such image`

### 2.4 Runtime Smoke Run

Run the same script again:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/phase2_manual_smoke.py
```

Interpretation:

- `orchestration_runtime=langgraph` means real `LangGraph` path is active
- `runtime=llama_cpp` for local model means real local LLM path is active
- `runtime=litellm` for fallback means real fallback path is active
- `verification_result.runner=docker` with `failure_kind=null` means Docker sandbox succeeded

## 3. Manual Acceptance Checklist

These checks map directly to Phase 2 and Phase 2.x goals.

### Query Pipeline

- `minder_query` returns an answer with sources
- workflow guidance includes `Current step: Test Writing`
- provider/runtime metadata are present
- transition log is present

### Workflow Enforcement

- the prompt is test-first for TDD state
- successful run advances workflow state to the next step
- guard failure does not advance workflow state

### Retrieval

- query/search automatically ingest the repo
- code search returns indexed code files from the repo
- retrieval mode is vector-backed when ingested documents exist

### Verification

- subprocess mode works in dev
- docker mode reports correct failure kinds when unavailable
- docker mode succeeds when image exists and the daemon is reachable

### Runtime Fidelity

- `LangGraph` path is used when dependency is installed
- local `llama_cpp` path is used when dependency and model file exist
- `LiteLLM` fallback path is used when dependency and API key exist

## 4. Decision Rule Before Phase 3

You can treat Phase 2 and Phase 2.x as ready for Phase 3 when:

- baseline mode passes fully
- runtime mode passes for the dependencies you intend to rely on in Phase 3
- Docker sandbox image exists and can run at least one Python snippet
- the smoke script output shows:
  - valid query answer
  - sources
  - workflow transition
  - verification result
  - code search hit
  - error search hit
