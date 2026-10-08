FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# curl only, for the container healthcheck. No compiler needed: psycopg[binary]
# and chromadb both ship wheels for this platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv from PyPI rather than `COPY --from=ghcr.io/astral-sh/uv` — ghcr.io is not
# reachable from the dev network, and PyPI is.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependency layer: cached unless pyproject/uv.lock change.
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --extra ai --no-install-project

COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --extra ai

# Bake the local embedding model (all-MiniLM-L6-v2, ~79MB) into the image.
# Otherwise every container start re-downloads it from S3, which on a slow link
# takes minutes and makes the healthcheck fail before the app is ready.
RUN uv run python -c "\
from chromadb.api.types import DefaultEmbeddingFunction; \
DefaultEmbeddingFunction()(['warmup']); \
print('embedding model cached')"

EXPOSE 8000
CMD ["uvicorn", "sendox_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
