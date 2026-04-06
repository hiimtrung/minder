.PHONY: all lint test check-all clean build-docker

all: lint test

lint:
	uv run ruff check .
	uv run mypy src

test:
	uv run pytest tests/unit tests/integration

check-all: lint test build-docker

clean:
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache build dist *.egg-info

build-docker:
	docker build -f docker/Dockerfile -t minder:latest .
