from __future__ import annotations

from pathlib import Path


def test_phase4_3_dockerfile_builds_dashboard_bundle() -> None:
    dockerfile = Path("docker/Dockerfile").read_text()

    assert "FROM oven/bun:1.2.21 AS dashboard-builder" in dockerfile
    assert "COPY src/dashboard/package.json" in dockerfile
    assert "RUN bun install" in dockerfile
    assert "RUN bun run build" in dockerfile
    assert "COPY --from=dashboard-builder /dashboard/dist /app/dashboard-dist" in dockerfile


def test_phase4_3_production_compose_serves_dashboard_bundle() -> None:
    compose = Path("docker/docker-compose.prod.yml").read_text()

    assert "MINDER_DASHBOARD__BASE_PATH: /dashboard" in compose
    assert "MINDER_DASHBOARD__STATIC_DIR: /app/dashboard-dist" in compose
    assert "MINDER_DASHBOARD__LEGACY_COMPAT_ENABLED: \"false\"" in compose
