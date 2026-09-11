# EvalOps backend image (Phase 10, CP 10.4).
#
# One image serves three roles, distinguished only by the container `command`:
#   - the FastAPI API           (uvicorn evalops.api.main:app)
#   - the Celery worker         (celery -A evalops.worker.celery_app:celery_app worker)
#   - the one-shot DB migration (alembic upgrade head)
# See docker-compose.yml for how each service uses this image.
#
# uv is pinned to the same version CI's astral-sh/setup-uv@v5 uses
# (.github/workflows/ci.yml) so a local build and CI resolve identically.

FROM ghcr.io/astral-sh/uv:0.12.10 AS uv

FROM python:3.11-slim AS builder
COPY --from=uv /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first (cached across source-only changes). --no-install-project
# resolves and installs only the locked dependencies, not evalops itself.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Now the project's own source, and install evalops itself (non-editable: the
# image does not rely on a source mount, and the venv is self-contained).
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.11-slim AS runtime

# Non-root runtime user. No shell login, no home-directory writes expected.
RUN groupadd --system evalops && \
    useradd --system --gid evalops --home-dir /app --no-create-home evalops

WORKDIR /app

COPY --from=builder --chown=evalops:evalops /app/.venv /app/.venv
COPY --from=builder --chown=evalops:evalops /app/src /app/src
COPY --from=builder --chown=evalops:evalops /app/alembic /app/alembic
COPY --from=builder --chown=evalops:evalops /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Structured JSON logging by default in a container (CP 10.3); override per
    # environment, never bake a secret in.
    EVALOPS_LOG_FORMAT=json

USER evalops

EXPOSE 8000

# No default HEALTHCHECK here -- the API, worker, and migration job need
# different checks (GET /ready, `celery inspect ping`, exit code respectively),
# defined per-service in docker-compose.yml against the endpoints CP 10.3 shipped.

# Default command runs the API; docker-compose.yml overrides `command:` for the
# worker and migration services.
CMD ["uvicorn", "evalops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
