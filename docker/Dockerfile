FROM oven/bun:1.2.21 AS dashboard-builder

WORKDIR /dashboard

COPY src/dashboard/package.json src/dashboard/astro.config.mjs src/dashboard/tsconfig.json /dashboard/
COPY src/dashboard/src /dashboard/src

RUN bun install
RUN bun run build

FROM python:3.14-slim

ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md minder.toml /app/
RUN uv sync --frozen

COPY src /app/src
COPY scripts /app/scripts
COPY --from=dashboard-builder /dashboard/dist /app/dashboard-dist

EXPOSE 8800

CMD ["uv", "run", "python", "-m", "minder.server"]
