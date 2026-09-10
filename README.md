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

### NOT YET SHIPPED

- Hosted provider execution — OpenAI, Anthropic
- Evaluation execution via the API
- Dashboard — the Next.js console in [dashboard/](dashboard/) covers browsing
  projects, a per-project workspace (Overview, Datasets, System Versions,
  Experiments, Release Policies), and creating / viewing datasets, system
  versions, and release policies against the real API. Creating and running
  experiments, and the results / comparison / release-decision views, are not
  built yet
- Statistical gating — bootstrap confidence intervals, significance, effect size
- RAG evaluation, agent evaluation, LLM-as-judge
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

### Repository layout

```
src/evalops/      Python package (domain model + Phase 1 CLI loop)
examples/         runnable offline example configs
tests/            test suite
docs/             architecture & project reference
.github/          CI workflows
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
