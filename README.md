# EvalOps

**Continuous Reliability Engineering for AI Systems**

> CI/CD for nondeterministic AI systems.

EvalOps is a continuous evaluation and release-gating platform for LLM, RAG, and
agent systems. Before a change ships, it runs the current production
configuration and the candidate configuration against a fixed evaluation
dataset, measures quality, cost, latency, and reliability for both, and produces
a release decision that a CI pipeline can enforce.

**Worked example.** A new prompt improves answer quality by 6% but increases p95
latency by 40%. The release policy allows a maximum 20% latency increase. EvalOps
fails the release check and blocks the CI pipeline — exactly as a failing unit
test would.

---

## The problem

AI applications change constantly — teams switch models, edit prompts, modify RAG
pipelines, adjust agent tool policies. Any of these can silently improve one
dimension (answer quality) while degrading another (latency, cost, tool
reliability, safety). Traditional software tests don't catch this: the failure is
statistical and behavioral, not a thrown exception. EvalOps makes that regression
class visible and gate-able.

### What EvalOps is not

- Not a model leaderboard ("model X scores higher than model Y on task Z")
- Not a chatbot or prompt playground
- Not a drag-and-drop agent builder
- Not a general-purpose RAG UI

It answers one narrow, practical question: *is this specific candidate version of
my specific application safe and good enough to ship, relative to what's already
in production?*

---

## The workflow

```
baseline  ->  candidate  ->  evaluate  ->  compare  ->  gate
```

```
AI system change (model / prompt / RAG config / agent tool policy)
        |
        v
Run the evaluation dataset against BASELINE and CANDIDATE
        |
        v
Measure: quality | cost | latency | tool use | safety
        |
        v
Statistical comparison (not a naive point comparison)
        |
        v
Apply release-policy thresholds
        |
        v
PASS -> allow release        FAIL -> block release (CI)
```

Longer term, failing production traces are promoted into the versioned regression
dataset, so every fixed bug becomes a permanent test case:
**measure -> compare -> gate -> observe -> learn -> re-evaluate.**

---

## Development status

**Phase 1 — core CLI evaluation loop (complete, locally verified).**
`evalops run config.yaml` runs a baseline-vs-candidate evaluation end to end.
Two execution backends, both verified: `mock` (built-in, deterministic, offline
— used by the checked-in examples and all CI) and `ollama` (real inference
against a local Ollama server). CI is fully offline and never requires Ollama.
The full design and phase plan live in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), which is the source of truth.

The sections below follow the discipline required by `docs/ARCHITECTURE.md §13`:
a feature is listed under **SHIPPED** only if its full path actually works today.

### SHIPPED (works today, verifiably)

- **Repo & tooling** — `src/` layout package, `uv` + committed `uv.lock`, Ruff
  (lint + format), mypy `--strict`, pytest, pre-commit, GitHub Actions CI on
  Python 3.11 and 3.12
- **Domain model** — frozen Project / Dataset / DatasetCase / SystemVersion /
  Experiment / EvaluationRun / CaseResult / EvaluationResult / MetricComparison /
  ReleasePolicy, plus the `Evaluator` and `ProviderClient` contracts
- **JSONL evaluation datasets** — `load_jsonl` with line-numbered validation
- **Deterministic offline execution** (`backend: mock`) — a configurable
  built-in `MockProvider` (exact rendered-prompt → response; synthetic
  token / latency / cost values); no network, no randomness
- **Real local execution** (`backend: ollama`) — `OllamaProvider` calls a local
  Ollama server (`POST /api/generate`, stdlib HTTP, no API key); usage metrics
  (`prompt_eval_count`, `eval_count`, `total_duration`) come straight from
  Ollama, `cost_usd` is 0.0. The evaluation / gating / reporting pipeline is
  unchanged — only the provider differs.
- **Deterministic evaluators** — `exact_match`, `contains`, `regex_match`
- **Baseline vs candidate comparison** — synchronous runner producing
  `EvaluationRun` / `CaseResult` records, with repeats and per-case failure
  isolation
- **Quality / cost / latency / reliability aggregation** — `success_rate`,
  `<evaluator>.pass_rate`, `latency_ms.mean`, `latency_ms.p95`, `cost_usd.total`
- **Release-policy gating** — fractional adverse-change thresholds, closed
  metric-direction rules, explicit zero-baseline handling, PASS / BLOCK
- **`evalops run`** — YAML config, human report on stdout, stable `--json`
  result output (`schema_version` 2, with per-metric `gate_outcome` and
  `advisories`), exit codes `0` (pass, incl. pass with advisories) / `1`
  (block) / `2` (error). The CLI gate routes through the same
  `run_evaluation` orchestration as the persisted/API path, so its release
  decision — statistical guard, blocking reasons and advisories — is identical
  to what the dashboard shows for equivalent data.
- **GitHub PR release gate** — [`.github/workflows/release-gate.yml`](.github/workflows/release-gate.yml)
  runs `evalops run <deterministic mock config> --json` on every `pull_request`
  (and `workflow_dispatch`), renders a `$GITHUB_STEP_SUMMARY` from the
  schema-v2 JSON (`python -m evalops.ci`, no re-derived logic), and always
  uploads the full JSON report as an artifact. The job fails only on a real
  BLOCK (exit 1) or an execution/config error (exit 2) — the summary keeps the
  two distinct; **PASS-with-advisories stays a PASS** (exit 0, green). Offline:
  `backend: mock`, no network, no `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.
- Worked examples: [examples/support/](examples/support/) — `regression.yaml`
  BLOCKs on a latency budget while quality improves; `fixed.yaml` PASSes;
  `ollama.yaml` is a real local smoke run, verified end to end against a local
  Ollama server (PASS, 4 cases / 8 runs / 0 failures), outside CI
- **Persistence** — PostgreSQL schema (SQLAlchemy 2.x + Alembic), domain↔ORM
  mapping, and repositories with a unit-of-work
- **Read/write API** — a small FastAPI app (`evalops.api.main:app`) over the
  repositories: create/read/list for projects, datasets, system versions,
  release policies, and experiments. No evaluation execution through the API yet.
- **Production trace foundation** (Phase 8, CP 8.1) — a minimal, validated
  `ProductionTrace` model (`input` / `output` / optional reference / metadata /
  latency / cost / error / origin), a `production_trace` PostgreSQL table
  (indexed by project / system version / recency), and thin ingestion/read
  endpoints: `POST` / `GET /projects/{id}/traces`, `GET /traces/{id}`. No
  headers/cookies/environment are captured; no redaction.
- **Trace → replayable regression dataset** (Phase 8, CP 8.2) — one backend
  operation (`evalops.promotion.promote_traces_to_dataset`) and one endpoint,
  `POST /projects/{id}/trace-datasets` `{ "name", "trace_ids": [...] }`, that
  promote selected traces into an **ordinary `Dataset`** — one `DatasetCase`
  per trace, in request order, carrying `input`, the recorded reference as the
  expected output (never `trace.output`), and `source_trace_id` (origin
  `promoted_trace`). Atomic; production traces are never mutated. The result
  runs through the existing Dataset → Experiment → Eval Runner → statistical
  evidence → release gate flow with **no trace-specific runner or path**.
- **Production Traces dashboard + replay workflow** (Phase 8, CP 8.3) — a
  *Production Traces* tab in the project workspace: a browse/select trace list
  (captured time, system version, input, output/error status, reference
  availability, latency, cost), a trace inspector (input, production output
  labelled *not* ground truth, reference, metadata, latency/cost/error,
  provenance), multi-select promotion with live reference coverage
  ("_3 of 5 selected traces have reference outputs_") and a non-blocking
  reference-less warning, and — on success — links to the created dataset and
  straight into the existing experiment form (`?dataset=` preselect). A small
  secondary "Add trace" form uses the existing POST endpoint with explicit
  fields only. No charts, no new evaluation semantics.
- **RAG evaluation foundation** (Phase 9, CP 9.1) — a provider execution result
  can carry framework-neutral **retrieval evidence** (`RetrievedItem`:
  `doc_id` / `content` / `rank` / optional `score`), threaded onto the run;
  `MockProvider` reports it deterministically. Three deterministic evaluators —
  `retrieval_recall`, `context_precision`, and `groundedness`
  (`groundedness_lexical`, an explicitly-labelled lexical-overlap approximation,
  *not* a hallucination detector) — score it against
  `DatasetCase.expected_retrieval_ids`. RAG metrics enter the **existing**
  aggregation → paired-bootstrap evidence → release gate as `<name>.pass_rate`,
  with no RAG-specific runner, experiment type, or gate. EvalOps evaluates
  retrieval behaviour; it does not own a vector DB, embeddings, or the retrieval
  pipeline. One narrow additive migration; text-only providers, runs, and
  datasets are unchanged.
- **Agent / tool evaluation foundation** (Phase 9, CP 9.2) — a provider
  execution result can carry framework-neutral **tool-call evidence**
  (`ToolCall`: `name` / `arguments` / `result` / `ok` / `error`, ordered),
  threaded onto the run; `MockProvider` reports it deterministically. Four
  deterministic evaluators — `tool_selection` (name-set Jaccard),
  `tool_arguments` (structural, key-order-independent JSON comparison — *not*
  semantic), `tool_success` (observed success rate), `tool_trajectory` (ordered
  name-sequence Dice — *exact adherence, not task correctness*) — score against
  `DatasetCase.expected_tool_calls`. EvalOps observes tool behaviour; it does
  not execute external tools or plan. Also lands a **generic
  `<evaluator>.mean_score` metric** for every evaluator (mean of
  `EvaluatorScore.score`, higher-is-better), so a graded regression that stays
  above an evaluator's pass threshold (recall 1.0 → 0.9, tool selection
  1.0 → 0.8) is still visible to a `ReleasePolicy` — through the existing
  aggregation / paired-bootstrap / gate path, no agent-specific logic. One
  narrow additive migration; `pass_rate` metrics and text-only / RAG runs
  unchanged.
- **RAG + agent evaluation dashboard** (Phase 9, CP 9.3) — the full Phase 9
  workflow in the existing console, no new pages: the dataset JSONL form/parser
  accept `expected_retrieval_ids` and ordered `expected_tool_calls`
  (`{name, arguments?}`) with example snippets, and dataset detail shows those
  expectations per case behind progressive disclosure; the experiment run form
  offers the shipped RAG (`retrieval_recall` / `context_precision` /
  `groundedness`) and agent (`tool_selection` / `tool_arguments` /
  `tool_success` / `tool_trajectory`) evaluators grouped by family, with only
  the backend thresholds (`min_recall` / `min_precision` / `min_groundedness` /
  `min_score`) and a "which need labels" hint; each persisted run row expands to
  its scores and, when present, a labelled **Retrieved context** and ordered
  **Tool trajectory** (readable blocks, not raw JSON); and `ReleaseDecision`
  renders human-readable RAG/agent metric names plus a *pass rate* vs *mean
  score* legend. No metric, statistic, or gate outcome is computed in the
  frontend — the backend stays authoritative. Text-only datasets/runs and
  production-trace replay are unchanged.
- **Dashboard UX foundation** (Phase 10, CP 10.1) — a coherent developer-tool
  shell: a grouped, responsive project sidebar (Overview / Evaluate / Production
  / Configuration / Advanced) replacing the horizontally-scrolling tab bar, with
  all existing routes preserved; a larger, restrained type scale and button
  hierarchy on shared primitives; an onboarding-focused Projects home
  ("Ship AI system changes with confidence" + a 5-step *How EvalOps works*); an
  actionable Project Overview with a real setup checklist (no fabricated
  analytics); a global **Help** drawer glossary (Dataset, System version,
  Experiment, Release policy, PASS/BLOCK, inconclusive evidence, …); and a
  lightweight accessible toast for resource-created feedback. Raw project UUIDs
  move into a low-emphasis "Project details" disclosure. No backend, API, or
  evaluation-semantics change; experiment result/evidence visuals are CP 10.2.
- **Experiment results + regression diagnostics** (Phase 10, CP 10.2) — the
  experiment page is now a decision-first surface: a comparison header
  (baseline → candidate, dataset, policy status, IDs behind "Technical
  details"), a dominant release-decision hero with four distinct states
  (PASS / BLOCK / passed-with-unverified-concerns / comparison-only), a grouped
  metric comparison (Quality / Reliability / Performance) with baseline-vs-
  candidate bars for [0,1] metrics only, and Phase 5 statistical evidence behind
  progressive disclosure. A new **deterministic regression-diagnostics** layer
  (`GET /experiments/{id}/diagnostics`, computed from persisted runs by
  `evalops.diagnostics`) explains a BLOCK at the case level — regressing pairs
  grouped into defensible categories (evaluator regression, provider/execution
  failure, retrieval / tool-selection / tool-argument / tool-execution /
  trajectory regression) with affected case ids and a representative pair for
  side-by-side inspection. **Diagnostics are explanatory only: they never change
  a PASS/BLOCK decision, add a gate, or run a second statistical engine.** No
  change to statistical thresholds, `MIN_PAIRS_TO_BLOCK`, release-policy
  semantics, or the async execution path.
- **Production observability + operational health** (Phase 10, CP 10.3) — a
  small coherent `evalops.obs` layer, standard library only. Centralised
  **structured JSON logging** (`configure_logging` / `log_event`) with stable
  event names (`http_request_completed`, `async_job_queued/started/completed/
  failed`, `experiment_started/completed`, `release_decision_computed`,
  `provider_call_completed/failed`) instead of scattered prose logs. A pure-ASGI
  `RequestContextMiddleware` resolves/validates `X-Request-ID` (generating one
  when absent), echoes it on the response, and logs one completion event per
  request; `contextvars`-based correlation (`request_id` / `project_id` /
  `experiment_id` / `job_id` / `celery_task_id`) propagates concurrency-safely
  from an HTTP request through the async job to the Celery task and the
  experiment/provider calls beneath it, with no process-global mutable state.
  `GET /health` (liveness, no dependency) is now distinct from `GET /ready`
  (PostgreSQL + Redis connectivity, correct 503 when a required one is down,
  Redis correctly optional via `EVALOPS_REQUIRE_REDIS=false`); both carry safe
  build metadata (service/version/environment/revision from the environment,
  never fabricated). A redaction helper (`evalops.obs.redact`) strips
  credential-shaped substrings from any logged exception; prompts, model
  output, dataset/trace content and API keys are never logged. No new
  execution path, no retries, no evaluation/gate/statistical/diagnostics
  semantics change. OpenTelemetry was evaluated and explicitly deferred —
  structured logs + correlation ids are sufficient for this checkpoint (see
  `docs/ARCHITECTURE.md` §7.9).
- **Runtime resilience + containerization** (Phase 10, CP 10.4) — the whole
  application runs as a production-shaped `docker compose up` stack (dashboard,
  API, worker, PostgreSQL, Redis) with no change to evaluation/gate/persistence
  semantics. One non-root backend image (`Dockerfile`) serves the API, the
  worker, and a dedicated one-shot `alembic upgrade head` migration job that
  both must wait on (`service_completed_successfully`) before starting, so
  migrations never race; a multi-stage Next.js **standalone** image
  (`dashboard/Dockerfile`) serves the dashboard, its `/api/*` proxy moved from
  a build-time-baked `next.config.ts` rewrite into a request-time server-side
  proxy (`src/app/api/[...path]/route.ts` — a Node.js-runtime Route Handler;
  see CP 10.5 below for why it isn't Proxy/Middleware) so the same built image
  can point at any API location via `API_PROXY_TARGET` at container start.
  Container health checks reuse the
  CP 10.3 `/health`/`/ready` endpoints and Celery's own `inspect ping` — no new
  health mechanism. The worker deliberately keeps Celery's **at-most-once**
  task delivery (`task_acks_late=False`) so a crashed worker is never
  automatically redelivered a nondeterministic, possibly-billed evaluation; a
  generous configurable time limit is a safety net against a hung task, not a
  retry. This makes a worker-death mid-run a **stale `running` job** with a
  documented, manual recovery procedure rather than a scheduler/reaper
  subsystem (deferred). Verified with a real `docker compose up --build`:
  create → async-run → Celery execution → persisted PASS/BLOCK decision →
  full-stack restart with data intact, all correlated end-to-end by the
  CP 10.3 `request_id`. See `docs/ARCHITECTURE.md` §7.10.
- **API security + Azure production deployment** (Phase 10, CP 10.5) — a
  single portfolio-scale **API key** (`EVALOPS_API_KEY`, `Authorization:
  Bearer <key>`, constant-time comparison, `evalops.security`) protects every
  route except `/health`/`/ready` (platform probes stay open); unset, it is a
  no-op (every existing local/dev/test flow is unaffected), but the API now
  **refuses to start** with `EVALOPS_ENV=production` and no key configured.
  The dashboard's server-side proxy attaches the key itself
  (`EVALOPS_API_KEY`, server-only, never sent to the browser); curl/CLI usage
  authenticates the same way. Baseline security response headers, and CORS
  that is off by default (no wildcard, no credentials, opt-in origins only —
  the dashboard never calls the API cross-origin, only through its own
  proxy). Interactive `/docs`/`/redoc`/`/openapi.json` are disabled in
  production. The already-verified Azure Container Apps topology (dashboard /
  API / worker Container Apps, a Container Apps Job for migrations, ACR,
  managed identity + `AcrPull`, PostgreSQL Flexible Server, Redis as a
  Container App) is now codified as reproducible scripts
  (`deploy/azure/*.sh`) and a manually-triggered, OIDC-authenticated GitHub
  Actions workflow (`.github/workflows/deploy-azure.yml` — no stored Azure
  password/service-principal secret) that runs the same checks CI runs, builds
  linux/amd64 images tagged with the immutable commit SHA, runs the migration
  job and stops if it fails, then rolls `api`/`worker`/`dashboard` forward and
  smoke-checks them. See `docs/ARCHITECTURE.md` §7.11 and
  `deploy/azure/README.md`.

### NOT YET SHIPPED

- Hosted provider execution — OpenAI, Anthropic
- Evaluation execution via the API
- Statistical gating — bootstrap confidence intervals, significance, effect size
- RAG generation-quality metrics beyond lexical groundedness; semantic trajectory / agent-correctness judging
- Cloud deployment

`MockProvider` is deterministic test infrastructure for offline development and
CI — **not** model inference. `OllamaProvider` is real local model inference.

### COMMITTED (current milestone — Phase 2)

- Persistence + API: FastAPI, PostgreSQL, SQLAlchemy, Alembic — re-running an
  experiment reproduces its stored configuration

### ROADMAP (planned next, in order)

| Phase | Deliverable |
|---|---|
| 1 | Core CLI eval engine: JSONL dataset -> model execution -> evaluation -> results (`evalops run config.yaml`) |
| 2 | Persistence + API: FastAPI, PostgreSQL, SQLAlchemy, Alembic |
| 3 | Full-stack UI: Next.js console (Projects, Datasets, Experiments, Compare, Run detail, Release decision) |
| 4 | Distributed execution: Redis + Celery, retries, idempotency, cancellation |
| 5 | Statistical evaluation: repeated sampling, bootstrap CI, paired comparison, effect size |
| 6 | Judge calibration: labeled calibration set, agreement metrics (Cohen's κ, precision/recall/F1) |
| 7 | GitHub CI gate: PR-triggered `evalops run --json` workflow, PR step summary, non-zero exit on a real BLOCK (shipped) |
| 8 | Production trace -> regression case loop: ingestion, viewer, promote-to-regression, dataset versioning |
| 9 | RAG + agent evaluation, extending the same evaluator abstraction |
| 10 | Polish: structured logging -> OpenTelemetry, optional Grafana, one cloud deployment |

### VISION

A single system that closes the reliability loop for AI applications: every
candidate change is evaluated against production with statistical rigor;
regressions in quality, cost, latency, tool use, and safety block the release
automatically in CI; LLM-as-judge evaluators are calibrated against a
human-labeled set rather than trusted blindly; RAG retrieval and agent
trajectories are evaluated as first-class concerns; and every failure observed in
production becomes a permanent regression case that no future candidate can
silently reintroduce. One `docker compose up` reproduces the whole system
locally; one hosted instance is enough to run it for real.

---

## High-level architecture

V1 (built first — synchronous, no queue):

```
Next.js dashboard
      |
      v
   FastAPI  ------------------>  PostgreSQL
      |
      v
 Eval Runner
      |
      v
 Provider Layer  -->  OpenAI . Claude . Ollama (local)
```

Execution is synchronous in V1 to prove the domain model and the evaluation
pipeline end to end. The target architecture (evaluation scheduler, Redis task
queue, worker pool, trace service, analytics layer, `pgvector` for trace
clustering) is adopted only once synchronous execution is a demonstrated
bottleneck — the rationale and full diagram are in
[docs/ARCHITECTURE.md §5](docs/ARCHITECTURE.md).

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Database | PostgreSQL (+ pgvector later) |
| Frontend | Next.js, TypeScript, Tailwind |
| Worker execution (Phase 4+) | Celery + Redis |
| CI | GitHub Actions |
| Infra | Docker Compose locally -> one hosted instance |

The backend (FastAPI + PostgreSQL) is implemented; the frontend is in progress
(Projects screen only); the worker layer is future work. The table describes the
committed design.

---

## Development

Requires **Python 3.11+** and [**uv**](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd EvalOps

uv sync                     # create .venv and install dev tooling
uv run pre-commit install   # optional: enable local git hooks
```

Common tasks (`make <target>`, or the underlying command):

| Task | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Format check | `uv run ruff format --check .` |
| Type check | `uv run mypy` |
| Tests | `uv run pytest` |
| All of the above | `make check` |

CI runs the same lint, format, type, and test checks on Python 3.11 and 3.12 for
every push to `main` and every pull request.

### Run an evaluation

Fully offline and deterministic — no API keys, no network:

```bash
uv run evalops run examples/support/regression.yaml        # -> BLOCK, exit 1
uv run evalops run examples/support/fixed.yaml             # -> PASS,  exit 0
uv run evalops run examples/support/fixed.yaml --json - --quiet   # JSON only
```

`--json PATH` also writes the machine-readable result to a file. All numbers in
these examples come from the built-in deterministic mock provider, not a real
model.

Exit codes (the CI contract): **`0`** = PASS, including a PASS that carries
advisories (a threshold was breached but the evidence is too weak to block);
**`1`** = release BLOCK; **`2`** = configuration / execution / provider / judge
error (no release decision produced).

### GitHub PR release gate

`.github/workflows/release-gate.yml` gates pull requests. On each PR it runs the
deterministic evaluation above, writes the schema-v2 JSON to a file, uploads
that file as the **`evalops-report`** artifact (always, when it exists), and
publishes a PR **Step Summary** — PASS / BLOCK / ERROR heading, blocking
reasons, advisories, and a compact metric table — rendered by
`python -m evalops.ci` straight from the JSON (it never re-computes a decision).
The workflow **fails only on exit 1 (BLOCK) or exit 2 (error)**, and the summary
keeps those two cases distinct. A PASS with advisories is green. Run it manually
with **Actions → EvalOps Release Gate → Run workflow** (optionally pointing
`config` at `examples/support/regression.yaml` to see the BLOCK path).

To run against a real local model instead, install [Ollama](https://ollama.com),
start it (`ollama serve`), pull a model (`ollama pull llama3.2`), and:

```bash
uv run evalops run examples/support/ollama.yaml
```

Outputs and latency are then real and vary between runs. This path is not
exercised by CI.

### Run the API

Requires a PostgreSQL database. Point `DATABASE_URL` at it (see
[.env.example](.env.example)), apply the schema, then start the app:

```bash
export DATABASE_URL=postgresql+psycopg://evalops:evalops@localhost:5432/evalops
uv run alembic upgrade head
uv run uvicorn evalops.api.main:app --reload      # or: make api
```

Interactive docs at `http://127.0.0.1:8000/docs`. The API is create/read/list
only — it does not run evaluations yet.

### Run the dashboard

The web console lives in [dashboard/](dashboard/) (Next.js + TypeScript +
Tailwind). It proxies `/api/*` to the FastAPI server above.

```bash
cd dashboard
npm install                 # first time
npm run dev                 # http://localhost:3000  -> /projects
```

Set `API_PROXY_TARGET` (see `dashboard/.env.example`) if the API is not on
`http://127.0.0.1:8000`. Checks: `npm run check` (lint + typecheck + test +
build); CI runs the same on Node 22. Implemented so far: the projects list, the
per-project workspace, and dataset / system-version / release-policy management.

### Run the background worker (Phase 4)

The Celery worker runs an experiment off the request path through the same
`execute_experiment_in_uow(...)` service the API uses. It needs a Redis broker
and the same `DATABASE_URL`. Redis is broker-only; PostgreSQL stays the source
of truth.

```bash
docker compose -f infra/docker-compose.yml up -d redis   # broker (or run your own Redis)
export CELERY_BROKER_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql+psycopg://evalops:evalops@localhost:5432/evalops
uv run celery -A evalops.worker.celery_app worker --loglevel=info
```

Queue a run through the API — this writes a durable `async_job` row
(`queued → running → completed | failed`) and dispatches the task:

```bash
curl -sX POST localhost:8000/experiments/<experiment-id>/run-async \
  -H 'content-type: application/json' \
  -d '{"execution": {"backend": "mock"}, "evaluators": [{"type": "contains"}]}'
# -> 202 { "id": "<job-id>", "status": "queued", ... }

curl -s localhost:8000/jobs/<job-id>        # poll until status is completed / failed
```

`enqueue_experiment_run(...)` is the same call from Python. The worker moves the
job through its states and persists `EvaluationRun` / `EvaluationResult` rows
exactly as the synchronous `POST /experiments/{id}/run` does; PostgreSQL — not
Redis — is the authoritative record of job status.

### Run the full stack with Docker (Phase 10, CP 10.4)

`docker compose up --build` (or `make compose-up`) brings up the entire
application — dashboard, API, worker, PostgreSQL, Redis — as a
production-shaped container stack, with the same evaluation/gate/persistence
semantics as the flows above:

```bash
cp .env.example .env
# Required as of CP 10.5 -- this stack runs with EVALOPS_ENV=production by
# default, and the API now refuses to start in production without a key:
echo "EVALOPS_API_KEY=$(openssl rand -hex 32)" >> .env
docker compose up --build
open http://localhost:3000
```

**Topology** — `browser → dashboard (:3000) → api (:8000) → postgres` /
`redis ← worker`. `postgres` and `redis` are not published to the host by
default (uncomment their `ports:` in `docker-compose.yml` if you need direct
access); service-to-service traffic uses Compose's own DNS
(`postgres`, `redis`, `api` as hostnames), fixed in `docker-compose.yml` —
not read from `.env`, which is for the non-containerized flow above instead.

**Images** — one backend image (`Dockerfile`, multi-stage `uv sync --locked`,
non-root user) serves the API, the worker, *and* the one-shot migration job,
distinguished only by the container `command:`. The dashboard
(`dashboard/Dockerfile`) is a multi-stage Next.js **standalone** build — no
dev server, no `node_modules` beyond what's traced, non-root user. Both build
in CI (`.github/workflows/ci.yml`, `docker` job) on every push/PR; neither is
published anywhere yet.

**Migrations** — a dedicated one-shot `migrate` service runs
`alembic upgrade head` and exits; `api` and `worker` both wait for it to
*succeed* (`service_completed_successfully`) before starting, so neither races
the other to migrate and a migration failure blocks both. Safe to re-run on
every restart (`alembic upgrade head` against a current schema is a no-op).

**Health/readiness** — container health checks reuse the CP 10.3 endpoints,
not a new mechanism: `api`'s check is `GET /ready` (Postgres + Redis
reachability, no LLM provider involved); `postgres`/`redis` use their own
standard probes (`pg_isready`, `redis-cli ping`); `worker`'s is
`celery inspect ping` (a real round-trip through the broker to the worker
process); `dashboard`'s is a plain HTTP probe (it has no `/health` of its own
— that is the API's concern). `dashboard` waits on `api`'s health,
`api`/`worker` wait on `redis`'s health and `migrate`'s success.

**Celery delivery semantics** — the worker keeps **at-most-once** task
delivery (`task_acks_late=False`): a worker dying mid-evaluation is never
retried, because a repeated provider call is neither free nor deterministic.
See `src/evalops/worker/celery_app.py`'s module docstring and
`docs/ARCHITECTURE.md` CP 10.4 for the full rationale, the resulting
**stale-job** limitation (a job stuck at `running` after a worker dies is not
auto-recovered in this checkpoint), and the manual recovery procedure.

**Ollama and container networking** — Ollama is not part of this Compose
stack (only Mock is used for the deterministic path above); if you point a
`SystemVersion` at Ollama running on your host while the API/worker run in
containers, `localhost` inside a container means the container itself, not
your host. Use `OLLAMA_BASE_URL=http://host.docker.internal:11434` on Docker
Desktop (macOS/Windows); on Linux, either add
`extra_hosts: ["host.docker.internal:host-gateway"]` to the service or point
at the host's real LAN/bridge address — there is no single value that works
identically everywhere, so this is left as an explicit override rather than a
hard-coded guess.

Stop everything with `docker compose down` (add `-v` only if you want to
delete the `postgres_data` volume and start clean).

### API security (Phase 10, CP 10.5)

A single API key (`EVALOPS_API_KEY`), not OAuth/user accounts/RBAC —
appropriate for a portfolio deployment, not a claim of enterprise auth. Unset,
every request is allowed (local dev / the test suite are unaffected); set,
every route except `GET /health`/`GET /ready` requires
`Authorization: Bearer <key>` (constant-time comparison, `evalops.security`).
`EVALOPS_ENV=production` **requires** it — the API refuses to start otherwise.
The dashboard's server-side proxy (`dashboard/src/app/api/[...path]/route.ts`)
attaches the same key itself from its own `EVALOPS_API_KEY`; it never reaches
the browser. CORS is off by default (no wildcard, no credentials — set
`EVALOPS_CORS_ALLOWED_ORIGINS` only for a genuine direct-from-browser
integration; the dashboard itself never needs it). See
`docs/ARCHITECTURE.md` §7.11 for the full model and its limitations.

### Deploy to Azure (production, Phase 10, CP 10.5)

The proven Azure topology — Container Apps for dashboard/API/worker, a
Container Apps Job for migrations, ACR, managed identity + `AcrPull`,
PostgreSQL Flexible Server, Redis as a Container App — is codified as
reproducible scripts and a GitHub Actions workflow rather than click-ops:

- **One-time setup, fresh subscription**: `deploy/azure/00-provision-infra.sh` →
  `deploy/azure/01-provision-apps.sh` → `deploy/azure/03-github-oidc.sh`, then
  configure the repo's `production` GitHub Environment (required reviewers +
  the variable names `03-github-oidc.sh` prints).
- **Already-provisioned Container Apps** (created by hand): run
  `deploy/azure/04-adopt-existing.sh` instead — it only wires up the new
  `EVALOPS_API_KEY`/`EVALOPS_ENV` settings on the existing apps and never
  recreates infrastructure. Never run `00-provision-infra.sh` /
  `01-provision-apps.sh` against resources they didn't create.
- Full walkthrough, variable/secret table, and the honest tradeoffs
  (Redis-as-Container-App, Postgres public access) are in
  **`deploy/azure/README.md`** — read that before running anything.
- **Every deploy after setup**: Actions tab → "Deploy to Azure (production)" →
  Run workflow. The same checks CI runs always run first. Blank `image_tag`
  then builds the checked-out commit and pushes it to ACR; a supplied
  `image_tag` skips the build entirely and redeploys/rolls back that existing
  ACR tag **without rebuilding it** (and without ever overwriting it). Either
  way: OIDC login (no stored Azure password/service-principal secret) → run
  the Alembic migration job (the deploy stops here if it fails) → roll
  `api`/`worker`/`dashboard` forward, each with a deploy-unique revision
  suffix → a bounded post-deploy health/smoke check, including a call through
  the dashboard's proxy — with no credential supplied by the workflow — to
  prove its server-side API-key injection actually works.
- No Terraform/Bicep — plain, reviewable `az` CLI scripts
  (`deploy/azure/*.sh`), each idempotent (safe to re-run) and independently
  shellcheck-clean.

### Repository layout

```
src/evalops/      Python package (domain model + Phase 1 CLI loop)
examples/         runnable offline example configs
tests/            test suite
docs/             architecture & project reference
.github/          CI workflows
Dockerfile        backend image (API / worker / migration job)
docker-compose.yml  full containerized stack (Phase 10, CP 10.4)
deploy/azure/     Azure deployment scripts + docs (Phase 10, CP 10.5)
```

Additional top-level directories (`datasets/`, `dashboard/`, `infra/`, ...) are
created only when their phase begins, so an impressive directory name never hides
an empty stub.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: small logically-scoped changes,
Conventional Commit messages, feature branches for real features, and
lint + format + type + tests green before a PR merges. `main` stays in a working
state.

---

## License

[MIT](LICENSE) © 2026 Sanjyot Amritkar
