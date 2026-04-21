# Development Workflow

This guide covers the common development tasks for Minder using the provided `Makefile`.

## Prerequisites

Before running these commands, ensure you have:
- `uv` installed.
- Docker and Docker Compose (for integration tests and container builds).

## Common Commands

| Command | Description |
| --- | --- |
| `make lint` | Run code quality checks (Ruff and Mypy) |
| `make test` | Run fast unit and integration tests |
| `make test-slow` | Run heavy subprocess-based tests (SSE/stdio) |
| `make test-all` | Run the full test suite |
| `make check-all` | Run lint, all tests, and verify docker builds |
| `make build-docker` | Build local API and Dashboard docker images |
| `make clean` | Remove build artifacts and caches |

## Release Workflow

Minder uses a two-step automated release process designed to work with branch protection rules on `main`.

### 1. Starting a Release
To bump the version and prepare a release:

```bash
make release-start VERSION=0.2.2
```

This command will:
1. Run local verification (lint + tests).
2. Create a new branch `chore/release-v0.2.2`.
3. Capture any unpushed local commits from your local `main`.
4. Reset your local `main` to match `origin/main`.
5. Update `pyproject.toml` version.
6. Push the branch and open a Pull Request (requires `gh` CLI).

### 2. Finalizing a Release
Once the Pull Request is merged into `main`:

```bash
make release-tag VERSION=0.2.2
```

This command will:
1. Switch to `main` and pull the latest changes.
2. Create an annotated tag `v0.2.2`.
3. Push the tag to trigger the GitHub Actions release workflow.

## Docker Builds

To verify Docker builds locally:

```bash
make build-docker
```

This builds `minder-api:latest` and `minder-dashboard:latest` using the optimized production Dockerfiles.
