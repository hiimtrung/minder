.PHONY: all lint test test-slow test-all check-all clean build-docker

all: lint test

lint:
	uv run ruff check .
	uv run mypy src

# Fast path: skip subprocess-spawning integration tests marked @pytest.mark.slow.
test:
	uv run pytest tests/unit tests/integration -m "not slow"

# Slow path: only the heavy subprocess-based tests (SSE/stdio round-trips).
test-slow:
	uv run pytest tests/integration -m "slow"

# Full suite (fast + slow). Use for local verification before release.
test-all:
	uv run pytest tests/unit tests/integration

check-all: lint test-all build-docker

clean:
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache build dist *.egg-info

build-docker:
	docker build -f docker/Dockerfile.api -t minder-api:latest .
	docker build -f docker/Dockerfile.dashboard -t minder-dashboard:latest .
