from __future__ import annotations

from pathlib import Path


def test_phase4_3_production_dockerfiles_exist_for_api_and_dashboard() -> None:
    api_dockerfile = Path("docker/Dockerfile.api").read_text()
    dashboard_dockerfile = Path("docker/Dockerfile.dashboard").read_text()
    caddyfile = Path("docker/Caddyfile").read_text()
    install_script = Path("scripts/release/install-minder-release.sh").read_text()
    full_compose = Path("docker/docker-compose.full.yml").read_text()
    dockerignore = Path(".dockerignore").read_text()

    assert "FROM python:3.14-slim AS api-builder" in api_dockerfile
    assert "UV_PROJECT_ENVIRONMENT=/app/.venv" in api_dockerfile
    assert "uv sync --frozen --no-dev --no-install-project --no-editable" in api_dockerfile
    assert "COPY --from=api-builder /app/.venv /app/.venv" in api_dockerfile
    assert 'CMD ["uv", "run", "--extra", "server", "python", "-m", "minder.server"]' in api_dockerfile

    assert "FROM oven/bun:1.2.21 AS dashboard-builder" in dashboard_dockerfile
    assert "COPY src/dashboard/package.json" in dashboard_dockerfile
    assert "bun install --frozen-lockfile" in dashboard_dockerfile
    assert "RUN bun run build" in dashboard_dockerfile
    assert 'CMD ["node", "dist/server/entry.mjs"]' in dashboard_dockerfile

    assert "reverse_proxy dashboard:8808" in caddyfile
    assert "reverse_proxy minder-api:8801" in caddyfile
    assert "__REPO_OWNER__" in install_script
    assert "releases/download" in install_script
    assert 'curl -fsSL "$RELEASE_BASE_URL/docker-compose.yml"' in install_script
    assert "MINDER_API_IMAGE" in install_script
    assert "MINDER_DASHBOARD_IMAGE" in install_script
    assert "ollama" in install_script
    assert 'dockerfile: docker/Dockerfile.api' in full_compose
    assert 'dockerfile: docker/Dockerfile.dashboard' in full_compose
    assert ".venv" in dockerignore
    assert "dist" in dockerignore
    assert "tests" in dockerignore


def test_phase4_3_production_compose_uses_gateway_dashboard_and_api_services() -> None:
    compose = Path("docker/docker-compose.yml").read_text()

    assert "gateway:" in compose
    assert "dashboard:" in compose
    assert "minder-api:" in compose
    assert 'ghcr.io/hiimtrung/minder-api:latest' in compose
    assert 'ghcr.io/hiimtrung/minder-dashboard:latest' in compose
    assert '${MINDER_PORT:-8800}:8800' in compose
    assert 'MINDER_SERVER__PORT: 8801' in compose
    assert 'MINDER_LLM__PROVIDER: ollama' in compose
    assert 'host.docker.internal' in compose


def test_phase4_3_release_workflow_uses_buildx_cache_for_images() -> None:
    release_workflow = Path(".github/workflows/release.yml").read_text()

    assert "cache-from: type=gha,scope=minder-api" in release_workflow
    assert "cache-to: type=gha,mode=max,scope=minder-api" in release_workflow
    assert "cache-from: type=gha,scope=minder-dashboard" in release_workflow
    assert "cache-to: type=gha,mode=max,scope=minder-dashboard" in release_workflow


def test_phase6_powershell_installer_has_release_placeholders_and_core_steps() -> None:
    installer = Path("scripts/release/install-minder-release.ps1").read_text()

    assert "__REPO_OWNER__" in installer
    assert "__REPO_NAME__" in installer
    assert "__RELEASE_TAG__" in installer
    assert "Invoke-WebRequest" in installer
    assert "& docker @composeArgs pull" in installer  # argv form, not shell string
    assert "& docker @composeArgs up -d" in installer
    assert "docker-compose.yml" in installer
    assert "Caddyfile" in installer
    assert ".minder-release.json" in installer
    assert "MINDER_INSTALL_DIR" in installer
    assert "ollama" in installer.lower()


def test_phase6_release_workflow_publishes_both_installers() -> None:
    release_workflow = Path(".github/workflows/release.yml").read_text()

    assert "install-minder-release.sh" in release_workflow
    assert "install-minder-release.ps1" in release_workflow
    assert "install-minder-${{ needs.build-dist.outputs.release_tag }}.ps1" in release_workflow
    assert "install-minder-${{ needs.build-dist.outputs.release_tag }}.sh" in release_workflow
