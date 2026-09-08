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

**Pre–Phase 0 — repository initialization.** The repo currently contains project
scaffolding only: packaging, tooling, CI, and design documentation. **No
evaluation, provider, persistence, API, or UI functionality exists yet.** The
full design and phase plan live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
which is the source of truth.

The sections below follow the discipline required by `docs/ARCHITECTURE.md §13`:
a feature is listed under **SHIPPED** only if its full path actually works today.

### SHIPPED (works today, verifiably)

- `evalops` Python package skeleton (`src/` layout, typed, version metadata only
  — no logic)
- Dependency management with `uv` and a committed `uv.lock`
- Lint + format (Ruff), type checking (mypy `--strict`), tests (pytest)
- Pre-commit hooks and a `Makefile` of common tasks
- GitHub Actions CI running lint, format check, type check, and tests on Python
  3.11 and 3.12
- Architecture & project reference document

There is intentionally **no `evalops` command yet.**

### COMMITTED (current milestone — Phase 0)

Freeze the core contracts, with no UI, no persistence, and no live model calls:

- Data model: Project, Dataset, DatasetCase, SystemVersion, Experiment,
  EvaluationRun, CaseResult, EvaluationResult, ReleasePolicy
- `Evaluator` interface (one contract for deterministic, statistical, and
  LLM-judge evaluators)
- `ProviderClient` interface (one contract for all model calls)
- Exit criterion: schema and interfaces reviewed and stable

### ROADMAP (planned next, in order)

| Phase | Deliverable |
|---|---|
| 1 | Core CLI eval engine: JSONL dataset -> model execution -> evaluation -> results (`evalops run config.yaml`) |
| 2 | Persistence + API: FastAPI, PostgreSQL, SQLAlchemy, Alembic |
| 3 | Full-stack UI: Next.js console (Projects, Datasets, Experiments, Compare, Run detail, Release decision) |
| 4 | Distributed execution: Redis + Celery, retries, idempotency, cancellation |
| 5 | Statistical evaluation: repeated sampling, bootstrap CI, paired comparison, effect size |
| 6 | Judge calibration: labeled calibration set, agreement metrics (Cohen's κ, precision/recall/F1) |
| 7 | GitHub CI gate: `evalops gate` with non-zero exit on regression |
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

None of the backend / frontend / worker layers are implemented yet; the table
describes the committed design, not current code.

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

There is no application to run yet. The `evalops` CLI arrives in Phase 1.

### Repository layout

```
src/evalops/      Python package (skeleton; subpackages added per phase)
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
