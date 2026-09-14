# EvalOps

**Don't benchmark models. Benchmark AI systems.**

> CI/CD for nondeterministic AI systems.

EvalOps is a continuous evaluation and release-gating platform for LLM, RAG,
and agent systems. Before a change ships, it runs the current production
configuration (**baseline**) and the proposed change (**candidate**) against
the same fixed dataset, repeats each case enough times to be statistically
honest about it, and turns the comparison into a **PASS** or a **BLOCK** a CI
pipeline can enforce — the same way a failing unit test would.

**Worked example.** A new prompt improves answer quality by 6% but increases
p95 latency by 40%. The release policy allows a maximum 20% latency increase.
EvalOps fails the release check and blocks the pipeline.

This is not a model leaderboard, a chatbot, a prompt playground, or a
drag-and-drop agent builder. It answers one narrow, practical question: *is
this specific candidate version of my specific application safe and good
enough to ship, relative to what's already in production?*

---

## The problem

AI applications change constantly — teams switch models, edit prompts, modify
RAG pipelines, adjust agent tool policies. Any of these can silently improve
one dimension (answer quality) while degrading another (latency, cost, tool
reliability, safety). Traditional software tests don't catch this: the failure
is statistical and behavioral, not a thrown exception. EvalOps makes that
regression class visible and gate-able.

## The workflow

```mermaid
flowchart LR
    D[("Dataset\n(fixed cases)")] --> R[Eval Runner]
    B["Baseline\nsystem version"] --> R
    C["Candidate\nsystem version"] --> R
    R --> S["Paired-bootstrap\nstatistical evidence"]
    S --> G{Release policy}
    G -->|within tolerance| P["PASS"]
    G -->|breach, confirmed| K["BLOCK"]
    G -->|breach, weak evidence| A["PASS + advisory"]
```

Every case runs **N times** per version; baseline and candidate runs are
paired by case and repeat, and a deterministic percentile bootstrap produces a
95% confidence interval for the change — not a naive point comparison. A
threshold breach only **BLOCK**s when there's enough paired evidence to
confirm it; a breach with too few samples surfaces as an **advisory** instead
of silently passing or blocking on noise. See [§8, ARCHITECTURE.md](docs/ARCHITECTURE.md#8-statistical-rigor)
for the full method.

Longer term, a failing production trace is promoted into the versioned
regression dataset, so every fixed bug becomes a permanent test case:
**measure → compare → gate → observe → learn → re-evaluate.**

## Architecture

```mermaid
flowchart TB
    UI["Next.js Dashboard"] -->|"/api/* proxy\n(server-side API key)"| API["FastAPI"]
    API --> PG[("PostgreSQL\nsource of truth")]
    API -->|enqueue async run| RD[("Redis\nbroker only")]
    RD --> W["Celery Worker"]
    W --> PG
    API --> PL["Provider Layer"]
    PL --> MP["MockProvider\n(deterministic, CI)"]
    PL --> OL["Ollama\n(local)"]
    PL --> OA["OpenAI / Anthropic\n(hosted)"]
```

Execution started synchronous, in-process, to prove the domain model and
evaluation pipeline before anything else — a queue was added only once
concurrent, isolatable, retryable runs were an actual requirement, not a
speculative one. The full V1 → current-architecture rationale is in
[ARCHITECTURE.md §5](docs/ARCHITECTURE.md#5-architecture).

PostgreSQL is always the authoritative record — of runs, results, and even
background-job status. Redis is broker-only for Celery; it holds nothing that
survival of the system depends on.

## Core capabilities

- **Statistical release gating** — paired bootstrap confidence intervals
  decide whether a threshold breach is real or noise; `MIN_PAIRS_TO_BLOCK`
  keeps a small sample from ever silently blocking a release. See
  [§8](docs/ARCHITECTURE.md#8-statistical-rigor).
- **RAG evaluation** — retrieval recall, context precision, and a
  lexically-labelled groundedness check score what a system retrieved,
  separately from what it answered. EvalOps scores retrieval evidence a
  system reports; it does not own a vector store or retrieval pipeline. See
  [§7.4](docs/ARCHITECTURE.md#74-implemented-rag-evaluation-foundation-phase-9-cp-91).
- **Agent evaluation** — tool selection, tool-argument correctness, success
  rate, and trajectory adherence, plus a graded `mean_score` metric so a
  regression that never crosses an evaluator's own pass/fail line is still
  visible to a release policy. See
  [§7.5](docs/ARCHITECTURE.md#75-implemented-agent--tool-evaluation-foundation-phase-9-cp-92).
- **Production trace → regression dataset** — capture a real interaction,
  promote a selection of failures into an ordinary, replayable `Dataset`
  through the *same* experiment/gate pipeline — no trace-specific runner. See
  [§7.1–7.3](docs/ARCHITECTURE.md#71-implemented-production-trace-foundation-phase-8-cp-81).
- **Judge calibration** — measures how often a configured LLM judge agrees
  with a small human-labeled set (agreement rate, precision/recall/F1).
  **Deliberately unconnected to release gating**: a low agreement rate never
  blocks a release or disables the judge, and it needs a real judge provider
  (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — there is no mock judge). See
  [§9](docs/ARCHITECTURE.md#9-judge-calibration-methodology).
- **Async execution** — a Celery/Redis worker runs an experiment off the
  request path, tracked by a durable PostgreSQL `async_job` row (never a
  Celery result backend). Delivery is deliberately **at-most-once**: a
  possibly-billed model call is never silently retried just because a worker
  died. See [§7.10](docs/ARCHITECTURE.md#710-implemented-runtime-resilience--containerization-phase-10-cp-104).
- **Security** — one portfolio-scale API key (`Authorization: Bearer <key>`,
  constant-time comparison), required outright in production; baseline
  security headers; CORS off by default. Not OAuth/RBAC — see limitations
  below. See [§7.11](docs/ARCHITECTURE.md#711-implemented-api-security--azure-production-deployment-phase-10-cp-105).
- **Observability** — structured JSON logs with stable event names, a
  request/job/task correlation id threaded end to end, `/health` (liveness)
  distinct from `/ready` (Postgres + Redis reachability). See
  [§7.9](docs/ARCHITECTURE.md#79-implemented-production-observability--operational-health-phase-10-cp-103).
- **CI/CD** — a GitHub Actions PR gate runs the deterministic mock evaluation
  on every pull request and fails the check on a real BLOCK; a separate,
  manually-triggered, OIDC-authenticated workflow deploys to Azure. See below.

No RAG-specific or agent-specific runner, gate, or statistics engine exists
anywhere in this list — every one of these extends the same evaluator
contract and flows through the same aggregation → statistical evidence →
release gate path.

---

## Quick start

Requires **Python 3.11+** and [**uv**](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd EvalOps
uv sync                     # create .venv and install dev tooling
uv run pytest               # 800+ tests, fully offline
```

### See a release decision in under a minute (no database, no API key)

```bash
uv run evalops run examples/support/regression.yaml   # -> BLOCK, exit 1
uv run evalops run examples/support/fixed.yaml         # -> PASS,  exit 0
```

Both are fully deterministic (`backend: mock`) — every number comes from the
built-in mock provider, not a real model.

### Run the full stack

```bash
cp .env.example .env
echo "EVALOPS_API_KEY=$(openssl rand -hex 32)" >> .env   # required: EVALOPS_ENV=production by default
docker compose up --build
open http://localhost:3000
```

Brings up the dashboard, API, worker, PostgreSQL, and Redis as one
production-shaped stack — see `make compose-up` and the
[Development](#development) section below for the non-containerized flow
(useful for iterating on one piece at a time).

### Deterministic demo: the Support Assistant scenario

```bash
uv run alembic upgrade head          # once, against a running Postgres
uv run uvicorn evalops.api.main:app &
make seed-demo
open http://localhost:3000/projects
```

`scripts/seed_demo.py` populates one project — *"EvalOps Demo — Support
Assistant"* — entirely through the public API (`MockProvider`, no network, no
credential) with a coherent, idempotent scenario: a clean **PASS**, a
statistically-confirmed **BLOCK** with real regression diagnostics, the exact
same regression re-evaluated on a smaller sample landing as a **PASS with an
advisory** instead (a concrete illustration of why a minimum sample size
exists), a RAG retrieval regression, an agent tool-use regression, and
production traces promoted into a replayable regression dataset. Safe to
re-run — it detects the existing project and does nothing further. See
**[docs/DEMO.md](docs/DEMO.md)** for the guided walkthrough.

### CLI / release-gate example

```bash
uv run evalops run examples/support/regression.yaml --json - --quiet
```

The real output (abridged — the full schema also carries `dataset` /
`baseline` / `candidate` / `repeats` / every per-metric `MetricLine`):

```json
{
  "schema_version": 2,
  "counts": {"cases": 4, "runs": 8, "failures": 0},
  "gated": true,
  "decision": "block",
  "reasons": ["latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)"],
  "advisories": []
}
```

Exit codes are the CI contract: **`0`** = PASS (including PASS with
advisories), **`1`** = BLOCK, **`2`** = config/execution/provider/judge error.
[`.github/workflows/release-gate.yml`](.github/workflows/release-gate.yml)
runs exactly this on every pull request and fails the check only on a real
BLOCK or an error — a PASS with advisories stays green.

---

## Repository structure

```
src/evalops/       Python package — domain model, evaluators, execution,
                    stats/gate, persistence, API, worker, CLI, security, obs
dashboard/          Next.js + TypeScript console
scripts/            seed_demo.py — the deterministic demo/seed script
examples/           runnable offline example configs (used by CI)
tests/              backend test suite (pytest)
dashboard/tests/    frontend test suite (vitest)
docs/               ARCHITECTURE.md (source of truth) + DEMO.md
.github/workflows/  CI, the PR release gate, and the Azure deploy workflow
Dockerfile          backend image (API / worker / migration job)
docker-compose.yml  full containerized stack
deploy/azure/       Azure provisioning scripts + deployment README
```

---

## Status

`docs/ARCHITECTURE.md` is the authoritative, checkpoint-by-checkpoint record —
this section is the condensed version. A feature is listed as **shipped**
only if its full path actually works today, end to end.

### Shipped

Core CLI evaluation loop (`evalops run`, deterministic mock + real Ollama /
OpenAI / Anthropic execution) · persistence + read/write API (PostgreSQL,
FastAPI) · the full dashboard console (projects, datasets, system versions,
experiments, release policies) · **paired-bootstrap statistical release
gating** with a PASS / BLOCK / advisory three-way decision · **RAG
evaluation** (retrieval recall, context precision, lexical groundedness) ·
**agent evaluation** (tool selection, arguments, success, trajectory, plus
graded `mean_score`) · **judge calibration** (agreement/precision/recall/F1
against human labels) · **production trace capture, promotion, and replay**
into the same experiment pipeline · deterministic **case-level regression
diagnostics** (explanatory only — never a second gate) · **async execution**
via Celery/Redis with a durable PostgreSQL job lifecycle · structured
**observability** (JSON logs, correlation ids, liveness/readiness) · **API-key
security** + baseline HTTP hardening · a full **Docker Compose** stack ·
**Azure Container Apps deployment**, provisioned by reproducible, idempotent,
shellcheck-clean scripts and rolled out by an OIDC-authenticated GitHub
Actions workflow · a **GitHub PR release gate** · a **deterministic seed/demo
script** for the whole system.

### Not yet shipped

- Semantic groundedness / hallucination detection (today's `groundedness`
  evaluator is an explicitly-labelled **lexical** overlap approximation, not
  a semantic judge)
- Semantic agent-task-correctness judging (today's agent evaluators check
  tool selection/arguments/trajectory *shape*, not whether the task was
  actually accomplished)
- Automatic recovery of a job stuck `running` after a worker crash (a
  documented manual recovery procedure exists; no reaper/heartbeat subsystem)
- OAuth / user accounts / RBAC (see [Limitations](#limitations--tradeoffs))

### Committed / roadmap

Nothing is currently committed beyond what's shipped above — Phase 10
(CP 10.1 through this portfolio-finish checkpoint) is complete. If this
project continued, the natural next candidates — none committed — are
OpenTelemetry (once structured logs+correlation ids prove insufficient),
`pgvector`-backed trace clustering (once failure volume justifies it), and a
semantic RAG/agent judge extending `LLMJudge` to take retrieval context or a
full trajectory as input.

### Vision

A single system that closes the reliability loop for AI applications: every
candidate change evaluated against production with statistical rigor;
regressions in quality, cost, latency, tool use, and safety blocked
automatically in CI; judges calibrated against human-labeled data rather than
trusted blindly; RAG retrieval and agent trajectories evaluated as first-class
concerns; every production failure becoming a permanent regression case no
future candidate can silently reintroduce.

---

## Limitations & tradeoffs

Stated plainly, not hidden in the fine print:

- **One flat API key, not multi-user auth.** Appropriate for a portfolio/
  single-operator deployment; not a claim of enterprise identity/RBAC.
- **Redis broker delivery is at-most-once, not at-least-once.** A worker
  dying mid-evaluation is never automatically retried, because a repeated
  model call is neither free nor deterministic — see
  `src/evalops/worker/celery_app.py`'s module docstring.
- **Judge calibration needs a real provider.** There is no mock LLM judge;
  calibrating one requires `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, or a
  reachable local Ollama.
- **Redis, in the shipped Azure/Compose topology, runs as a plain container**
  (`redis:7-alpine`, no persistence, single replica) — the portfolio-scale
  choice, not a claim it's the ideal managed-Redis architecture. Swapping in
  a managed Redis later is a `CELERY_BROKER_URL` change, nothing else.
- **PostgreSQL on Azure uses `--public-access 0.0.0.0`** (Azure-services-only,
  not the public internet), not a private VNet — this topology has none.
- **Groundedness/trajectory evaluators check shape, not semantic
  correctness** — see "Not yet shipped" above.
- **No Kubernetes, Kafka, pgvector, OpenTelemetry, or Prometheus/Grafana** —
  deliberately deferred per `docs/ARCHITECTURE.md`'s non-goals, not omitted
  by oversight.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL |
| Async execution | Celery + Redis (broker only) |
| Frontend | Next.js, TypeScript, Tailwind |
| Providers | Mock (deterministic), Ollama (local), OpenAI, Anthropic |
| CI/CD | GitHub Actions (PR release gate, Azure deploy) |
| Infra | Docker Compose (local) → Azure Container Apps (hosted) |

---

## Development

Common tasks (`make <target>`, or the underlying command):

| Task | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Type check | `uv run mypy` |
| Backend tests | `uv run pytest` |
| All of the above | `make check` |
| Dashboard checks (lint+typecheck+test+build) | `cd dashboard && npm run check` |
| Seed the demo scenario | `make seed-demo` |

CI runs the backend checks on Python 3.11/3.12 and the dashboard checks on
Node 22 for every push and pull request, plus a Docker build of both images.

### Run the API + dashboard without Docker

```bash
export DATABASE_URL=postgresql+psycopg://evalops:evalops@localhost:5432/evalops
uv run alembic upgrade head
uv run uvicorn evalops.api.main:app --reload      # http://127.0.0.1:8000/docs
```

```bash
cd dashboard && npm install && npm run dev          # http://localhost:3000
```

### Run the background worker

```bash
docker compose -f infra/docker-compose.yml up -d redis   # broker only
export CELERY_BROKER_URL=redis://localhost:6379/0
uv run celery -A evalops.worker.celery_app worker --loglevel=info
```

`POST /experiments/{id}/run-async` enqueues a durable job
(`queued → running → completed | failed`, tracked in PostgreSQL, not a Celery
result backend); `GET /jobs/{id}` polls it.

### Real local inference

```bash
ollama serve && ollama pull llama3.2
uv run evalops run examples/support/ollama.yaml
```

Outputs and latency are then real and vary between runs — not exercised by
CI. `examples/support/live-openai.yaml` shows the same shape against a hosted
provider (`OPENAI_API_KEY` required, never committed).

### Deploy to Azure

The Azure Container Apps topology (dashboard/API/worker, a migration Job, ACR,
PostgreSQL Flexible Server, Redis as its own Container App) is provisioned by
reproducible `az` CLI scripts (`deploy/azure/*.sh` — each idempotent and
independently shellcheck-clean; no Terraform/Bicep) and deployed by a
manually-triggered, OIDC-authenticated GitHub Actions workflow
(`.github/workflows/deploy-azure.yml` — no stored Azure password or
service-principal secret). **Read [`deploy/azure/README.md`](deploy/azure/README.md)
before running anything** — it has the full one-time setup, the
already-provisioned-infra adoption path, the GitHub Environment variable
table, and the honest tradeoffs. See also
[ARCHITECTURE.md §7.11](docs/ARCHITECTURE.md#711-implemented-api-security--azure-production-deployment-phase-10-cp-105).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: small logically-scoped
changes, Conventional Commit messages, lint + format + type + tests green
before a PR merges. `main` stays in a working state.

## License

[MIT](LICENSE) © 2026 Sanjyot Amritkar
