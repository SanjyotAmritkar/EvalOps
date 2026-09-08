# EvalOps — Architecture & Project Reference

**Status:** Design finalized, entering Phase 0 implementation
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
/gateway        provider clients (OpenAI, Anthropic, Ollama), cost/latency tracking
/eval           evaluators (deterministic, statistical, judge), rubrics, calibration
/datasets       versioned task sets (general/ + clinical/)
/api            FastAPI routes, auth, experiment orchestration
/worker         Celery tasks (Phase 4+)
/dashboard      Next.js app
/ci             evalops gate command + GitHub Actions workflow
/infra          docker-compose, Dockerfiles
/docs           this file and any supporting design docs
```

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