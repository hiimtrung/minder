# Development Workflow

This guide covers common development tasks for Minder using the provided `Makefile`.

## Prerequisites

| Tool             | Purpose                      |
| ---------------- | ---------------------------- |
| `uv`             | Python dependency management |
| `bun`            | Dashboard build (Astro)      |
| `rust` + `cargo` | Tauri desktop app (optional) |

## Common Commands

| Command               | Description                                             |
| --------------------- | ------------------------------------------------------- |
| `make native-install` | Install Python deps + build dashboard                   |
| `make native-run`     | Start server on :8800 (hot reload)                      |
| `make lint`           | Run code quality checks (Ruff and Mypy)                 |
| `make test`           | Run fast unit and integration tests                     |
| `make test-slow`      | Run heavy subprocess-based tests (SSE/stdio)            |
| `make test-all`       | Run the full test suite                                 |
| `make bundle`         | Build PyInstaller binary for Tauri sidecar              |
| `make app-dev`        | Run Tauri desktop app in dev mode                       |
| `make app-build`      | Build distributable Tauri app (.dmg / .deb / .AppImage) |
| `make clean`          | Remove build artifacts and caches                       |

## Dev Server

```bash
uv run python scripts/dev_server.py
```

Watches `src/**/*.py`, `.env`, and `minder.toml` and restarts on any change. Options:

```bash
uv run python scripts/dev_server.py --port 8810
uv run python scripts/dev_server.py --transport stdio
```

## Frontend Dev

```bash
bun run dev   # Astro dev server at http://localhost:8808/dashboard
```

API calls go to `http://localhost:8800` (configure via `PUBLIC_API_URL` in `src/dashboard/.env`).

## Lint and Type Check

```bash
make lint   # ruff check + ruff format + mypy
```

All three must pass before merging.

## Tests

```bash
make test       # unit + integration (fast)
make test-slow  # SSE/stdio subprocess tests
make test-all   # full suite
```

Tests use in-memory SQLite and in-memory vector store — no external services required.

## Release Workflow

Minder uses a two-step automated release process.

### 1. Starting a Release

```bash
make release-start VERSION=0.2.2
```

This will:

1. Run local verification (lint + tests)
2. Create branch `chore/release-v0.2.2`
3. Update `pyproject.toml` version
4. Push branch and open a Pull Request (requires `gh` CLI)

### 2. Finalizing a Release

Once the Pull Request is merged into `main`:

```bash
make release-tag VERSION=0.2.2
```

This will:

1. Switch to `main` and pull latest changes
2. Create an annotated tag `v0.2.2`
3. Push the tag to trigger the GitHub Actions release workflow
