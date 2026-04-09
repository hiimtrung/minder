from __future__ import annotations

from pathlib import Path


def test_phase4_3_production_dockerfiles_exist_for_api_and_dashboard() -> None:
    api_dockerfile = Path("docker/Dockerfile.api").read_text()
    dashboard_dockerfile = Path("docker/Dockerfile.dashboard").read_text()
    caddyfile = Path("docker/Caddyfile").read_text()
    install_script = Path("scripts/release/install-minder-release.sh").read_text()
    full_compose = Path("docker/docker-compose.full.yml").read_text()

    assert "PYTHONPATH=/app/src" in api_dockerfile
    assert 'CMD ["uv", "run", "python", "-m", "minder.server"]' in api_dockerfile

    assert "FROM oven/bun:1.2.21 AS dashboard-builder" in dashboard_dockerfile
    assert "COPY src/dashboard/package.json" in dashboard_dockerfile
    assert "RUN bun install --frozen-lockfile" in dashboard_dockerfile
    assert "RUN bun run build" in dashboard_dockerfile
    assert 'CMD ["node", "dist/server/entry.mjs"]' in dashboard_dockerfile

    assert "reverse_proxy dashboard:8808" in caddyfile
    assert "reverse_proxy minder-api:8801" in caddyfile
    assert "__REPO_OWNER__" in install_script
    assert "releases/download" in install_script
    assert 'curl -fsSL "$RELEASE_BASE_URL/docker-compose.yml"' in install_script
    assert "MINDER_API_IMAGE" in install_script
    assert "MINDER_DASHBOARD_IMAGE" in install_script
    assert 'dockerfile: docker/Dockerfile.api' in full_compose
    assert 'dockerfile: docker/Dockerfile.dashboard' in full_compose


def test_phase4_3_production_compose_uses_gateway_dashboard_and_api_services() -> None:
    compose = Path("docker/docker-compose.yml").read_text()

    assert "gateway:" in compose
    assert "dashboard:" in compose
    assert "minder-api:" in compose
    assert 'ghcr.io/hiimtrung/minder-api:latest' in compose
    assert 'ghcr.io/hiimtrung/minder-dashboard:latest' in compose
    assert '${MINDER_PORT:-8800}:8800' in compose
    assert 'MINDER_SERVER__PORT: 8801' in compose
