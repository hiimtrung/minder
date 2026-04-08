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

EXPOSE 8800

CMD ["uv", "run", "python", "-m", "minder.server"]
