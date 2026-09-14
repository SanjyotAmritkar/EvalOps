.PHONY: install lint fmt fmt-check type test check api dashboard \
	compose-up compose-down compose-logs seed-demo

install:
	uv sync

# Run the read/write API locally (needs DATABASE_URL + `alembic upgrade head`).
api:
	uv run uvicorn evalops.api.main:app --reload

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

fmt-check:
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest

check: lint fmt-check type test

# Frontend dashboard (see dashboard/). Needs Node; run `npm ci` in dashboard/ once.
dashboard:
	cd dashboard && npm run check

# Full containerized stack (Phase 10, CP 10.4): dashboard, api, worker,
# postgres, redis, plus a one-shot migration job. See docker-compose.yml and
# the README "Run the full stack with Docker" section.
compose-up:
	docker compose up --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f api worker

# Deterministic demo data (Phase 10, CP 10.6): populates "EvalOps Demo --
# Support Assistant" against a running API (default http://127.0.0.1:8000;
# override with EVALOPS_API_BASE_URL / --base-url). Idempotent -- safe to
# re-run. See docs/DEMO.md.
seed-demo:
	uv run python scripts/seed_demo.py
