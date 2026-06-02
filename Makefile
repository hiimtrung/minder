.PHONY: all lint test test-slow test-all check-all clean build-docker dev-install release-start release-tag dashboard-dev dashboard-build dashboard-check native-install native-run native-build native-dev bundle app-dev app-build

dev-install:
	uv tool install --editable . --force
	bun install

native-install:
	uv sync --extra server
	bun install
	bun run build

native-run: dashboard-build
	@rm -f ~/.minder/data/vectors.db/LOCK
	uv run python -m minder.server

# --- Phase 2: Bundle Python server as a PyInstaller binary ---

# Produce dist/minder-server-<target-triple> ready for Tauri sidecar.
# Requires PyInstaller: uv add --dev pyinstaller
#
# Unlike Docker builds (which use -DGGML_NATIVE=OFF for portability), native
# builds compile llama.cpp with full hardware acceleration:
#   macOS:  Metal GPU + Accelerate framewhisork (auto-detected)
#   Linux:  AVX2 / AVX-512 / FMA based on the build host CPU
#
# Override: CMAKE_ARGS="-DGGML_NATIVE=OFF" make bundle
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  NATIVE_CMAKE_ARGS ?= -DGGML_NATIVE=ON -DGGML_METAL=ON
else
  NATIVE_CMAKE_ARGS ?= -DGGML_NATIVE=ON
endif

bundle: dashboard-build
	@echo "Building PyInstaller bundle (native optimizations: $(NATIVE_CMAKE_ARGS))..."
	@command -v pyinstaller >/dev/null 2>&1 || uv add --dev pyinstaller
	CMAKE_ARGS="$(NATIVE_CMAKE_ARGS)" uv run pyinstaller minder-server.spec --clean --noconfirm
	@TARGET=$$(rustc -Vv | grep host | cut -d' ' -f2); \
	 echo "Copying sidecar for target: $$TARGET"; \
	 rm -rf "src-tauri/binaries/minder-server-$$TARGET" \
	        "src-tauri/binaries/_internal"; \
	 mkdir -p src-tauri/binaries; \
	 cp "dist/minder-server" \
	    "src-tauri/binaries/minder-server-$$TARGET"; \
	 chmod +x "src-tauri/binaries/minder-server-$$TARGET"; \
	 echo "Sidecar ready: src-tauri/binaries/minder-server-$$TARGET"


# --- Phase 3: Tauri desktop app ---

# Launch Tauri dev window (expects Python server already running via `make native-run`).
app-dev native-dev:
	bun run tauri dev

# Build the distributable desktop app (.dmg on macOS, .AppImage/.deb on Linux).
# Requires: `make bundle` first to create the sidecar binary.
app-build native-build: native-install bundle
	bun run tauri build

dashboard-dev:
	bun run dev

dashboard-build:
	bun run build

dashboard-check:
	bun run check

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

check-all: lint test-all

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
	echo "Checking out main and capturing any local commits into $$BRANCH_NAME..."; \
	git checkout main; \
	git fetch origin main; \
	git checkout -b $$BRANCH_NAME; \
	echo "Resetting local main to origin/main..."; \
	git checkout main; \
	git reset --hard origin/main; \
	git checkout $$BRANCH_NAME; \
	echo "Merging any new changes from origin/main..."; \
	git rebase origin/main; \
	echo "Updating version to $$CLEAN_VERSION in pyproject.toml..."; \
	sed -i.bak -e "s/^version = \".*\"/version = \"$$CLEAN_VERSION\"/" pyproject.toml && rm pyproject.toml.bak; \
	echo "Updating version to $$CLEAN_VERSION in src-tauri/tauri.conf.json..."; \
	python3 -c " \
import json, pathlib; \
p = pathlib.Path('src-tauri/tauri.conf.json'); \
cfg = json.loads(p.read_text()); \
cfg['version'] = '$$CLEAN_VERSION'; \
p.write_text(json.dumps(cfg, indent=2) + '\n') \
	"; \
	echo "Updating uv.lock..."; \
	uv lock; \
	if ! git diff --quiet pyproject.toml uv.lock src-tauri/tauri.conf.json; then \
		git add pyproject.toml uv.lock src-tauri/tauri.conf.json; \
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
