---
id: ses-1775191548
saved: 2026-04-03T11:45:48+07:00
status: active
---

# Session: Upgrade project virtual environment and repo Python baseline from 3.12 to 3.14.3; update tracked version markers and verify full quality gate on the new interpreter.

## Current Task
Upgrade project virtual environment and repo Python baseline from 3.12 to 3.14.3; update tracked version markers and verify full quality gate on the new interpreter.

## Next Steps
1. If desired, provision optional production runtimes: langgraph, llama-cpp-python, litellm, and Docker image minder-sandbox:latest.
2. Use docs/PHASE2_MANUAL_TEST.md and scripts/phase2_manual_smoke.py to run the full Phase 2 manual flow on the upgraded interpreter.

## Open Files
- pyproject.toml
- .python-version
- uv.lock
- docker/Dockerfile.sandbox
- docs/TASK_BREAKDOWN.md
- docs/plan/05-implementation-phases.md
- docs/plan/06-operations-and-delivery.md

## Recent Decisions
- Raise the project baseline from Python 3.12 to Python 3.14 and pin the active venv to CPython 3.14.3.
- Keep the existing uv-based environment management and verify the upgrade with ruff, mypy, and the full pytest suite.
- Update Docker sandbox and planning docs so repo metadata matches the new Python baseline.

