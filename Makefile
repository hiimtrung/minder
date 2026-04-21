.PHONY: all lint test test-slow test-all check-all clean build-docker release-start release-tag

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

release-start:
	@set -e; \
	if [ -z "$(VERSION)" ]; then \
		echo "Error: You must provide a VERSION, e.g., make release-start VERSION=0.0.1"; \
		exit 1; \
	fi; \
	echo "Running local verification (lint + tests)..."; \
	make lint test; \
	CLEAN_VERSION=$$(echo $(VERSION) | sed 's/^v//'); \
	BRANCH_NAME="chore/release-v$$CLEAN_VERSION"; \
	echo "Checking out main and pulling latest changes..."; \
	git checkout main; \
	git pull origin main; \
	echo "Creating branch $$BRANCH_NAME..."; \
	git checkout -b $$BRANCH_NAME; \
	echo "Updating version to $$CLEAN_VERSION in pyproject.toml..."; \
	sed -i.bak -e "s/^version = \".*\"/version = \"$$CLEAN_VERSION\"/" pyproject.toml && rm pyproject.toml.bak; \
	if ! git diff --quiet pyproject.toml; then \
		git add pyproject.toml; \
		git commit -m "chore(release): update version to v$$CLEAN_VERSION"; \
		git push -u origin $$BRANCH_NAME; \
		if command -v gh >/dev/null 2>&1; then \
			echo "Creating pull request..."; \
			gh pr create --title "chore(release): v$$CLEAN_VERSION" --body "Bump version to v$$CLEAN_VERSION for release." --base main; \
		else \
			echo "Branch pushed successfully. Please create a Pull Request to main manually."; \
		fi; \
	else \
		echo "Version is already $$CLEAN_VERSION in pyproject.toml."; \
	fi

release-tag:
	@set -e; \
	if [ -z "$(VERSION)" ]; then \
		echo "Error: You must provide a VERSION, e.g., make release-tag VERSION=0.0.1"; \
		exit 1; \
	fi; \
	CLEAN_VERSION=$$(echo $(VERSION) | sed 's/^v//'); \
	echo "Checking out main and pulling latest changes..."; \
	git checkout main; \
	git pull origin main; \
	if git rev-parse "v$$CLEAN_VERSION" >/dev/null 2>&1; then \
		echo "Error: Tag v$$CLEAN_VERSION already exists."; \
		exit 1; \
	fi; \
	echo "Creating and pushing tag v$$CLEAN_VERSION..."; \
	git tag -a "v$$CLEAN_VERSION" -m "Release v$$CLEAN_VERSION"; \
	git push origin "v$$CLEAN_VERSION"; \
	echo "Triggered release flow for v$$CLEAN_VERSION."
