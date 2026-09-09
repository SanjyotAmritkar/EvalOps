# EvalOps — Architecture & Project Reference

**Status:** Phases 0 and 1 shipped and locally verified — domain model frozen; the `evalops run` CLI evaluation loop works end to end with a deterministic mock backend (used by CI, which requires no network or Ollama) and a real local Ollama backend. Phase 2 (persistence + API) is next.
**Purpose of this document:** single source of truth for the system design, scope, roadmap, and acceptance criteria. Any contributor (human or tool-assisted) picking up this repo should be able to read this file and know exactly what to build next and why.

---

## 1. Problem Statement

AI applications change constantly — teams switch models, update prompts, modify RAG pipelines, or change agent tool configurations. Any of these changes can silently improve one dimension (e.g. answer quality) while degrading another (e.g. latency, cost, tool reliability). Traditional software tests do not catch this class of regression because the failure mode is statistical and behavioral, not a thrown exception.

## 2. Product Definition

**EvalOps** is a continuous evaluation and release-gating platform for LLM, RAG, and agent systems. Before a change ships, EvalOps runs the current production configuration and the candidate configuration against a fixed evaluation dataset, measures quality, cost, latency, and reliability for both, and produces a release decision.

**One-line pitch:** EvalOps is a continuous evaluation and release-gating platform that detects quality, cost, latency, and reliability regressions in LLM, RAG, and agent systems before they reach production.

**Tagline:** CI/CD for nondeterministic AI systems.

**Worked example:** A new prompt improves answer quality by 6% but increases p95 latency by 40%. The release policy allows a maximum 20% latency increase. EvalOps fails the release check and blocks the CI pipeline, exactly as a failing unit test would.

### What this is not
This is explicitly **not** a model leaderboard ("GPT scores higher than Claude on task X"). It answers a narrower, more practical engineering question: *is this specific candidate version of my specific application safe and good enough to ship, relative to what's already in production?*

## 3. Non-Goals (v1 and near-term)

To keep this a finishable, deeply-real system rather than a shallow, wide one, the following are explicitly out of scope until the core loop is proven:

- Not a generic chatbot or prompt playground
- Not a drag-and-drop agent builder
- Not a general-purpose RAG UI
- Not aiming for 15+ provider integrations — 2–3 hosted providers plus one local (Ollama) is enough
- No fine-tuning infrastructure
- No Kubernetes, no Kafka
- No large-scale failure clustering until there is real failure volume (hundreds to thousands of cases) to justify it
- No Prometheus/Grafana/OpenTelemetry until structured logging proves insufficient

## 4. System Concept Flow

```
AI system change (model / prompt / RAG config / agent tool policy)
        ↓
Run evaluation dataset against BASELINE and CANDIDATE
        ↓
Measure: quality | cost | latency | tool use | safety
        ↓
Statistical comparison (not naive point comparison)
        ↓
Apply release policy thresholds
        ↓
PASS → allow release      FAIL → block release (CI)
```

Longer-term: production traces that fail get promoted into the versioned regression dataset, so every fixed bug becomes a permanent test case. This closes the loop: **measure → compare → gate → observe → learn → re-evaluate.**

---

## 5. Architecture

### 5.1 V1 architecture (build this first — nothing else)

```
                Next.js (dashboard)
                       │
                       ▼
                    FastAPI
                       │
              ┌────────┴────────┐
              ▼                 ▼
         Eval Runner        PostgreSQL
              │
              ▼
        Provider Layer
        │      │      │
        ▼      ▼      ▼
     OpenAI  Claude  Ollama (local)
```

Execution is **synchronous** in V1. No queue, no workers. The goal of V1 is to prove the domain model and the evaluation pipeline end to end, not to prove distributed-systems skills prematurely.

### 5.2 Target architecture (evolve into this after V1 works)

```
                              Next.js
                          Evaluation Console
                                │
                                ▼
                           FastAPI (API Gateway)
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
          Experiment       Dataset         Trace Service
           Service         Service
                │               │
                └───────┬───────┘
                        ▼
                 Evaluation Scheduler
                        │
                        ▼
                      Redis (task queue)
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
         Worker 1    Worker 2    Worker N
            │           │           │
            └───────────┼───────────┘
                        ▼
                   LLM Gateway
               ┌────────┼─────────┐
               ▼        ▼         ▼
             GPT      Claude    Ollama
                        │
                        ▼
                  Evaluation Engine
                        │
               ┌────────┼─────────┐
               ▼        ▼         ▼
            Rules     Judge     Metrics
                        │
                        ▼
                   PostgreSQL (+ pgvector for trace clustering later)
                        │
                        ▼
                 Analytics Layer
```

Justify the migration explicitly in the README: *started synchronous to validate the domain model and evaluation pipeline; moved execution behind a queue once concurrent evaluation runs required isolation, retries, and horizontal scaling.*

### 5.3 Tech stack by layer

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic | Evaluation ecosystem is Python-native |
| Worker execution (Phase 4+) | Celery + Redis | Add only once sync execution is a proven bottleneck |
| Database | PostgreSQL (+ pgvector later) | Single source of truth for all runs |
| Frontend | Next.js, TypeScript, Tailwind | No Streamlit — this is a product, not a notebook |
| Observability (late-stage) | Structured JSON logs → OpenTelemetry → Prometheus/Grafana | Logs are sufficient for V1 |
| Infra | Docker Compose (local) → Render/Fly.io/ECS (one deployed instance) | No Kubernetes requirement |
| CI | GitHub Actions | Runs the `evalops gate` command on relevant PRs |

---

## 6. Data Model (freeze in Phase 0)

Core entities:

- **Project** — top-level container (e.g. "Customer Support Agent")
- **Dataset** — versioned collection of DatasetCases
- **DatasetCase** — a single input/expected-output pair (or reference), may originate from a hand-authored set or a promoted production trace
- **SystemVersion** — a named, versioned configuration: model, prompt template, RAG settings, tool policy
- **Experiment** — a comparison run between a baseline SystemVersion and a candidate SystemVersion over a Dataset
- **EvaluationRun** — one execution of one DatasetCase against one SystemVersion (captures raw output, latency, tokens, cost)
- **CaseResult** — the scored outcome of an EvaluationRun (per-evaluator scores)
- **EvaluationResult** — aggregated Experiment-level result (baseline vs candidate, per metric, with statistical comparison)
- **ReleasePolicy** — release-gate thresholds keyed by named metric (each value a fractional regression tolerance, e.g. `0.15` == 15%), plus an explicit `max_safety_violations` count. Representation only in Phase 0; metric directionality (higher- vs lower-is-better) and the PASS/FAIL gating logic are deferred to the later release-gating/statistical phase

Evaluator interface (unify all evaluator types behind one contract):

```python
class Evaluator:
    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        ...
```

An individual evaluator returns an `EvaluatorScore`. Multiple `EvaluatorScore`s for one run compose into a `CaseResult`; experiment-level aggregation of `CaseResult`s produces an `EvaluationResult`.

Three evaluator families implement this interface:
1. **Deterministic** — exact match, regex, JSON schema validation, code execution, tool-argument validation
2. **Statistical/ML** — embedding similarity, retrieval metrics (Recall@K, Precision@K, MRR)
3. **LLM Judge** — correctness, faithfulness, relevance, policy compliance (rubric prompts version-controlled in `/eval/rubrics`)

Provider interface (unify all model calls):

```python
class ProviderClient:
    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        # returns text, token usage, cost, latency
        ...
```

### 6.1 Provider adapters (Phase 6, CP 6.1)

One `ProviderClient` contract, four adapters:

| adapter | transport | credentials | usage / cost |
|---|---|---|---|
| `MockProvider` | none (deterministic) | none | synthetic test values |
| `OllamaProvider` | stdlib `urllib` → local `POST /api/generate` | none | Ollama's server-reported counts + `total_duration`; `cost_usd = 0` |
| `OpenAIProvider` | stdlib `urllib` → `POST /v1/chat/completions` | `OPENAI_API_KEY` (env only) | token counts from the response (`0` if absent, never guessed); `cost_usd = 0` (no pricing table); client-measured `latency_ms` |
| `AnthropicProvider` | stdlib `urllib` → `POST /v1/messages` | `ANTHROPIC_API_KEY` (env only) | as OpenAI (`input_tokens` / `output_tokens`) |

The hosted adapters use the repo's existing dependency-free HTTP pattern rather
than an SDK. API keys are read from the environment at call time only — never
stored on the object, logged, put in a run config, persisted, or serialised
into a Celery task. Every provider/network/API failure maps to `ProviderError`.
Adapters are built lazily, per provider actually used, so the local Ollama and
mock paths run with **no cloud credentials**.

**Cross-provider execution.** `ExecutionSpec.backend` selects the mode:
`mock` / `ollama` (unchanged), `openai` / `anthropic` (both versions on that
provider), and **`live`** — honour each `SystemVersion.provider` independently.
`live` is how a baseline and candidate on *different* providers/models are
compared (e.g. an Ollama/Llama baseline vs an OpenAI candidate, or OpenAI vs
Anthropic). `build_providers` returns a `{ProviderName: ProviderClient}` map;
`run_experiment` already dispatches each version to `providers[version.provider]`,
so nothing in the `Experiment` / `SystemVersion` model changes and there is no
special "compare providers" workflow — the existing experiment comparison is it.

### 6.2 LLM judge — a separate role (Phase 6, CP 6.1)

An **LLM judge is an evaluator, not a provider.** `LLMJudge` implements the
`Evaluator` contract (family `llm_judge`) and *uses* a `ProviderClient` of its
own — configured independently of the system under evaluation (its own
`provider` + `model`, low temperature by default). It renders a fixed,
version-controlled rubric over `(case input, candidate output, optional
reference)`, requires the judge to reply with one structured JSON verdict
(`pass`/`fail` + optional `score`), and turns that into the ordinary
`EvaluatorScore` that flows through aggregation and gating as
`<name>.pass_rate`. Malformed judge output raises `JudgeError` and aborts the
run loudly — it is never a silent pass. Judge-vs-human calibration/agreement
metrics are CP 6.2.

---

## 7. Evaluation Levels (build in this order, as extensions of the same core engine — never a separate subsystem)

1. **Model evaluation** — same prompt, different providers/models. Metrics: accuracy, latency, TTFT, cost, tokens, structured-output compliance.
2. **Prompt evaluation** — same model, different prompt versions. Adds experiment tracking (which prompt version produced which result).
3. **RAG evaluation** — retrieval quality (Recall@K, Precision@K, MRR, context relevance) evaluated *separately* from generation quality (faithfulness, answer relevance, citation correctness, context utilization). This is the domain module tied to the existing MediRAG/PubMed corpus (clinical QA faithfulness and hallucination rate).
4. **Agent evaluation** — evaluates not just the final answer but the trajectory: tool selection accuracy, tool argument correctness, unnecessary tool calls, loop detection, completion rate, token usage, policy violations. A run's trajectory is stored as an ordered list of tool_call/tool_result steps.
5. **Production trace → regression case** — a failed production trace can be promoted (`Add to regression suite`) into a new dataset version. Every future candidate must pass it. This is the flagship differentiator; build it right after the core loop is solid, before infra polish.

---

## 8. Statistical Rigor

Do not compare raw averages (`0.86 > 0.84`) and declare a winner. LLM outputs are nondeterministic, so:

- Run each case **N times** per SystemVersion (not just once)
- Compute mean, variance, and a bootstrap confidence interval per metric
- Use paired comparison between baseline and candidate (same cases, same N)
- Release policy example:
  ```
  quality improvement > 2%
  AND 95% CI does not overlap a regression beyond threshold
  AND cost increase < 10%
  AND p95 latency regression < 15%
  ```

### 8.1 Implemented approach — paired bootstrap (Phase 5, CP 5.1)

`evalops.stats` adds statistically defensible comparison primitives *alongside*
Phase 1 aggregation. It does not change `EvaluationResult`, `ReleasePolicy`, or
the PASS/BLOCK gate — those still run on point comparisons. It produces one
`MetricEvidence` object per gateable metric for a later gating phase / API to
consume.

**Pairing.** Baseline and candidate runs are matched by `(case_id,
repeat_index)`; only keys present on *both* sides are used ("comparable pairs"),
ordered by that key so the result is deterministic. Provider-failure handling is
per metric: `success_rate` and `<evaluator>.pass_rate` are per-run binary
indicators where a failed run contributes `0.0` (same denominator rule
aggregation uses); `latency_ms.mean` drops any pair where either side errored (a
failed run has no meaningful latency, and the drop count is recorded);
`cost_usd.mean` keeps every pair (a failed call genuinely costs ~0). Unmatched
runs (a key on only one side — corrupt/partial data) are counted and excluded.

**Statistic.** For each metric the estimator is the paired delta of means,
`mean(candidate_i − baseline_i)`. The CI is a **percentile bootstrap**: resample
the paired differences with replacement (`random.Random(seed)`, fixed default
seed, default 2000 resamples, default 95%) and take the empirical quantiles.
`ci_excludes_zero` is reported but is only meaningful when
`insufficient_evidence` is false (fewer than 3 comparable pairs → point
estimates only, no interval). A zero-variance difference sample collapses the
interval to a point.

**Why paired bootstrap** (not a t-test / Bayesian / analytic CI): LLM metrics
are bounded, discrete (pass rates), skewed (latency, cost) and evaluated at
small N — a normal-theory interval is not justified. Pairing on the same case +
repeat removes per-case difficulty variance, so the bootstrap is over the
*differences* and needs no distributional assumption. It is transparent, has no
heavy dependency (standard library only), and is deterministic given the seed so
CIs are reproducible in tests and stored results. `latency_ms.p95` and
`cost_usd.total` stay point-only for now (a paired bootstrap of a percentile /
total at small N is not defensible).

### 8.2 Statistical release gating (Phase 5, CP 5.2)

`evaluate_gate` reads `EvaluationResult.evidence` directly (no separate
argument), so the synchronous `/run`, the Celery worker, and the `GET
/results` recompute all gate identically. The **policy threshold still defines
the maximum tolerated adverse effect**; the statistical evidence only decides
whether a *breach* is trustworthy enough to BLOCK.

**Direction (closed mapping).** `success_rate` and `<evaluator>.pass_rate` are
higher-is-better; `latency_ms.mean`, `latency_ms.p95`, `cost_usd.total` are
lower-is-better. Adverse change is a *decrease* for higher-is-better and an
*increase* for lower-is-better, expressed as a fraction of the baseline
(matching the pre-Phase-5 point gate).

**Per-metric outcome.** For each gated `MetricComparison`:

1. `threshold_breached` — the point adverse change exceeds the policy
   threshold (unchanged deterministic test; a lower-is-better metric rising
   from a zero baseline is an unbounded breach).
2. If not breached → `pass`.
3. If breached and the metric has **no** `MetricEvidence` (`latency_ms.p95`,
   `cost_usd.total`) → `regression` → **BLOCK** (pre-Phase-5 behaviour, intact).
4. If breached and `n_pairs < MIN_PAIRS_TO_BLOCK` (8) or the bootstrap produced
   no CI → `regression_low_evidence` → **does not block** (advisory).
5. If breached, enough pairs, and the delta CI lies **entirely on the adverse
   side of the tolerated boundary** → `regression` → **BLOCK**.
6. Otherwise → `regression_inconclusive` → **does not block** (advisory).

**CI vs. the tolerated boundary** (not vs. zero — `ci_excludes_zero` alone is
never used). With `ref = evidence.baseline.mean` and tolerated fraction `t`:

| direction | tolerated boundary on `delta = candidate.mean − baseline.mean` | confirms a regression when |
|---|---|---|
| higher_is_better | `delta ≥ −t·ref` | `ci_high < −t·ref` |
| lower_is_better | `delta ≤ +t·ref` | `ci_low > +t·ref` |

**Minimum pairs.** `gate.MIN_PAIRS_TO_BLOCK = 8`, a fixed constant this phase
(distinct from `stats.MIN_PAIRS_FOR_CI = 3`, the floor for computing any CI at
all). A paired percentile bootstrap needs enough distinct pairs that its tail
quantiles reflect a distribution rather than one or two runs; 8 (e.g. 4 cases ×
2 repeats, or 8 × 1) is deliberately conservative. It is not a `ReleasePolicy`
field because `thresholds` is a flat `metric → float` map — a per-policy knob
would need a domain field, a column and a migration, exceeding "very little
complexity". Teams gain power by raising `repeats` or dataset size.

**Decision, reasons, advisories.** The release BLOCKs iff any verdict is
`regression`. `GateReport.reasons` lists only those (unchanged strings, so the
CLI/report output and existing consumers are unaffected). `GateReport.advisories`
is new: one line per `regression_inconclusive` / `regression_low_evidence`
breach, so a threshold breach that statistics could not confirm is surfaced
loudly while the release still PASSes. `MetricLineRead.gate_outcome` carries the
per-metric outcome; `regression` (the field driving BLOCK) is unchanged.

**Persistence / API.** Evidence is stored in a flat `metric_evidence` child
table of `evaluation_result` (like `metric_comparison`; the three
`SampleSummary` value objects are flattened to `*_mean` / `*_median` /
`*_stdev`, their `n` is always `n_pairs`). `RunResponse` and
`EvaluationResultRead` gain additive `advisories: []` and
`evidence: [MetricEvidenceRead]`; `GET /results` reconstructs `MetricEvidence`
from the table and recomputes an identical decision, so evidence and the
statistical verdict survive a page refresh.

**CLI.** `evalops run` stays a deterministic point-comparison gate
(`aggregate_results` produces no evidence, so `evaluate_gate` takes the
deterministic path). Statistical gating applies to the persisted execution
path only.

---

## 9. Judge Calibration Methodology

LLM-as-judge is only credible if it's measured against a labeled set — never judge-evaluating-judge.

**Stage 1 (during evaluator development):** hand-label 30–50 examples. Purpose: find broken rubric wording, ambiguous cases, judge bias, output-schema issues. No resume claim made from this stage.

**Stage 2 (once evaluator design is stable):** freeze a labeled calibration set of 100–150 examples. Compute exact agreement, binary pass/fail agreement, precision, recall, F1, Cohen's κ (and weighted κ or Spearman correlation for ordinal scores).

**Honesty requirement:** document this as a **manually labeled calibration set**, not "human-validated ground truth" — the author is a single annotator. If time allows, independently double-label a subset (e.g. 40 of the 150) to report human↔human agreement alongside judge↔consensus agreement. This is a stronger, more defensible claim than most projects attempt.

Store calibration artifacts explicitly:
```
calibration/
├── examples.jsonl
├── human_labels.jsonl
├── judge_predictions.jsonl
└── calibration_report.json
```

### 9.1 Implemented: binary agreement calibration (CP 6.2)

`evalops.calibration.calibrate_judge(judge, examples)` runs a configured
`LLMJudge` (CP 6.1) over a list of `LabeledJudgeExample`
(`input`, `output`, optional `reference`, human `human_pass`) and returns a
`JudgeCalibration`:

* **flow** — for each example the judge is run once via `LLMJudge.judge(...)`.
  A `ProviderError` or `JudgeError` on an example is recorded on that
  `JudgeCalibrationCase` (`judge_pass = None`, `error` set) and **excluded from
  every metric** — never counted as agreement. Any other exception propagates.
* **metrics** (`JudgeCalibrationMetrics`, positive class = "pass"):
  `total`; `scored` = examples the judge returned a verdict for; `failures`;
  `agreements` = TP + TN and `agreement_rate` = agreements / scored; the
  confusion matrix `TP` (human & judge pass) / `TN` (both fail) / `FP` (judge
  pass, human fail) / `FN` (judge fail, human pass); `precision` = TP/(TP+FP),
  `recall` = TP/(TP+FN), `f1` = harmonic mean. Every ratio is `None` (not `0`)
  when its denominator is zero.
* **inspection** — every `JudgeCalibrationCase` keeps the human verdict and the
  judge's verdict, score, and reasoning.

**Persistence / API.** `judge_calibration` (+ `judge_calibration_case` child)
store the judge's identity and config metadata — provider, model, name,
temperature, `rubric_id` — the aggregate metrics, and every scored case.
**Never a credential.** Standalone: no experiment/project foreign key.
`POST /judge-calibrations` runs and persists one; `GET
/judge-calibrations/{id}` retrieves it.

**Semantics.** Calibration is pure measurement of judge trustworthiness. It is
deliberately unconnected to the Phase 5 release gate: a low agreement rate does
**not** reject or disable a judge, and gate behaviour is unchanged. V1 is
binary pass/fail only — Cohen's κ, ordinal scores, significance, and
auto-gating are out of scope.

---

## 10. Phased Build Plan

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Data model, evaluator interface, provider interface frozen. No UI. | Schema and interfaces reviewed and stable |
| 1 | Core CLI eval engine: JSONL dataset → model execution → evaluation → results | `evalops run config.yaml` works end to end against a real provider |
| 2 | Persistence + API: FastAPI, PostgreSQL, SQLAlchemy, Alembic | Re-running an experiment reproduces its stored configuration |
| 3 | Full-stack UI: Next.js — Projects, Datasets, Experiments, Compare, Run detail, Release decision | Every number in the UI comes from persisted execution data, nothing mocked |
| 4 | Distributed execution: Redis + Celery, retries, idempotency, cancellation | Kill a worker mid-run and verify recovery |
| 5 | Statistical evaluation: repeated sampling, bootstrap CI, paired comparison, effect size | Release policy is statistically grounded, not a naive point comparison |
| 6 | Judge calibration: build the labeled calibration set, compute agreement metrics | `calibration_report.json` exists and is referenced in the README |
| 7 | GitHub CI gate: `evalops gate` with non-zero exit on regression | A deliberately bad candidate turns a GitHub Actions check red |
| 8 | Production trace feedback loop: trace ingestion, trace viewer, promote-to-regression, dataset versioning | A traced failure becomes a permanent regression case |
| 9 | RAG + agent evaluation, extending the existing evaluator abstraction | No separate evaluation subsystem was built to support this |
| 10 | Polish: structured logging → OpenTelemetry, Grafana if useful, one real cloud deployment, failure clustering as a stretch feature | `docker compose up` reproduces the full system locally |

---

## 11. Acceptance Test (the actual definition of "done")

The project is done when this sequence runs live, with no hand-waving and no stubbed components:

1. Open the dashboard
2. Show production system v1
3. Create candidate v2
4. Run evaluation against the full case set
5. Watch execution process cases (sync in V1, workers from Phase 4)
6. Compare baseline vs candidate
7. Show individual case-level regressions
8. Explain the statistical result (not just a point comparison)
9. Show calibrated-evaluator evidence (the calibration report)
10. Candidate intentionally violates a release threshold
11. GitHub Actions check fails
12. Fix the candidate
13. Re-run
14. Evaluation passes
15. GitHub release gate turns green

Stretch (once Phase 8 exists):

16. Show a failed production trace
17. Promote it to the regression dataset
18. Re-run the candidate against the updated dataset
19. Demonstrate the same failure can no longer ship silently

---

## 12. Repository Structure

```
/gateway            provider clients (OpenAI, Anthropic, Ollama), cost/latency tracking
/eval               evaluators (deterministic, statistical, judge), rubrics, calibration
/datasets           versioned task sets (general/ + clinical/)
/api                FastAPI routes + request/response schemas (adapts HTTP to the service)
/execution_service  persisted experiment execution: load → run → persist → gate, HTTP-independent
/worker             Celery worker: broker = Redis, one task -> execution_service (Phase 4)
/dashboard          Next.js app
/ci                 evalops gate command + GitHub Actions workflow
/infra              docker-compose, Dockerfiles
/docs               this file and any supporting design docs
```

Experiment orchestration lives in `evalops.execution_service`, not in the API
routes. It takes an experiment id plus the non-persisted run configuration and
owns loading entities, running the pipeline, persisting runs/results, and
applying the release gate. It has two entry points that differ only in
transaction ownership: `execute_experiment(session, ...)` where the caller's
unit of work owns commit/rollback (the FastAPI request path), and
`execute_experiment_in_uow(sessions, ...)` which opens its own unit of work for
callers with no request-scoped session. The service never commits a
caller-supplied session.

`evalops.worker` realises that second path: a Celery app (`celery_app.py`,
Redis broker, no result backend) and a single task (`tasks.py`,
`evalops.execute_experiment`). No evaluation, gating, or persistence logic
lives in the worker; it rebuilds the typed config via the same
`ExecutionOptions` and calls `execute_experiment_in_uow` with a per-process
session factory.

**Durable job lifecycle.** An `async_job` row in PostgreSQL -- not Celery -- is
the authoritative status of a background run (`domain.AsyncJob`,
`AsyncJobRepository`). `enqueue_experiment_run` writes a `queued` job then
dispatches the task with the **job id**. The task then:

```
queued --(mark_running)--> running --(mark_completed + result link)--> completed
                              |
                              +--(exception -> mark_failed, bounded error)--> failed
```

Each transition is its own unit of work, separate from the evaluation's unit
of work. The evaluation runs via `execute_experiment_in_uow` (its own
transaction); if it fails and rolls back, the task opens a *fresh* transaction
to mark the job `failed`, so a failed evaluation is never left as a job stuck
at `running`. Terminal states (`completed` / `failed`) are immutable;
`AsyncJobRepository` rejects illegal transitions with `RecordConflict`. No
distributed locking. A hard worker crash between `running` and a terminal
state is out of scope here (Phase 4 recovery/reaping is later).

Redis is broker-only; runs and results are written to PostgreSQL through the
execution service.

**Async API.** `POST /experiments/{id}/run-async` validates the same
`RunRequest` the sync route uses, calls `enqueue_experiment_run` (which commits
a `queued` job in its own unit of work, then dispatches the Celery task), and
returns **202** with the job (`AsyncJobRead`). `GET /jobs/{job_id}` returns the
job's current row. Status always comes from PostgreSQL, never from a Celery
result backend (there is none). If the job row commits but broker dispatch
fails, `enqueue_experiment_run` marks the job `failed` and raises
`DispatchError`; the route returns **500** and `GET /jobs/{id}` shows the
`failed` job -- dispatch failure never returns 202. Structural request errors
are synchronous 422s; a bad evaluator config surfaces later as a `failed` job.
The synchronous `POST /experiments/{id}/run` is unchanged.

Python code is packaged under an installable `src/evalops/` package (src layout). The frozen Phase 0 domain model lives at `src/evalops/domain/`. The entries above are `evalops` submodules — `evalops.gateway`, `evalops.eval`, `evalops.api`, `evalops.worker`, `evalops.ci` — not top-level directories; non-Python trees (`datasets/`, `dashboard/`, `infra/`, `docs/`) stay at the repository root. Each is created only when its phase begins.

## 13. README Structure

The README must distinguish, explicitly, in separate sections:

- **VISION** — everything EvalOps could become (the full ambition)
- **ROADMAP** — features likely to be implemented next
- **COMMITTED** — features required for the current milestone
- **SHIPPED** — features that actually work today, verifiably

This prevents the failure mode where a reviewer opens a module and finds an unfinished stub behind an impressive-sounding directory name. Only list a feature under SHIPPED if the full acceptance-test path for it works.

## 14. Deployment

- Local: single `docker compose up` brings up frontend, backend, worker, redis, postgres
- Hosted (one instance is enough): frontend → Vercel; backend + worker → Render/Fly.io/ECS; Postgres → managed Postgres; Redis → managed Redis
- No Terraform, no Kubernetes required for this project's scope

## 15. Positioning Notes

- Preferred name: **EvalOps — Continuous Reliability Engineering for AI Systems**
- Avoid describing this as "LLM Benchmarking Platform" — that framing undersells it and reads as generic
- The tagline "CI/CD for nondeterministic AI systems" should appear in the README opening line, followed immediately by the worked example from Section 2 before any architecture diagram