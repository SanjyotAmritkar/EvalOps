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
| CI | GitHub Actions | Runs `evalops run --json` on relevant PRs and gates the merge |

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

### 7.1 Implemented: production trace foundation (Phase 8, CP 8.1)

The **storage half** of level 5 is shipped. Promotion + replay landed in CP 8.2
(§7.2); the dashboard workflow in CP 8.3 (§7.3).

`domain.ProductionTrace` is a frozen, validated value model for one real
interaction: `project_id`, `system_version_id`, `created_at`, `input`,
`output`, optional `reference_output`, optional free-form `metadata`, optional
`latency_ms` / `cost_usd` / `error`, and an `origin` marker
(`TraceOrigin.PRODUCTION`). It is **not** an observability schema — no spans,
trace trees, OpenTelemetry types, token streams, or tool-call event graphs.

Persistence is one leaf table, `production_trace` (PostgreSQL source of truth,
Alembic migration `9f2bb314ccd0`): `project_id` / `system_version_id` /
`created_at` indexed, `metadata` as JSON/JSONB, both FKs `ON DELETE CASCADE`,
`latency_ms` / `cost_usd` non-negative CHECKs. `ProductionTraceRepository`
(`add` / `get` / `list_for_project`, oldest-first) follows the existing
repository + unit-of-work pattern; a trace is write-once, so there is no update.

Ingestion is three thin FastAPI routes reusing existing patterns:
`POST /projects/{project_id}/traces` (validates the project and the referenced
system version exist → 404, and that the version belongs to the project → 422;
persists; returns 201), `GET /projects/{project_id}/traces`, and
`GET /traces/{trace_id}`. List returns persisted data only, all rows, in a
deterministic order — no pagination, filtering, or search infrastructure.

**Data handling.** Only the JSON body is read: no request headers, cookies, or
environment are captured, `metadata` is stored exactly as supplied, and no new
code logs trace values. There is no redaction/PII framework — callers are
responsible for sending only data they are permitted to evaluate.

### 7.2 Implemented: trace → replayable regression dataset (Phase 8, CP 8.2)

Selected production traces are promoted into an **ordinary `Dataset`** so real
interactions replay through the *existing* pipeline. There is **no second
runner and no trace-specific evaluation path**:

```
ProductionTrace ──promote──▶ DatasetCase(source_trace_id, origin=promoted_trace)
                             └─▶ Dataset ─▶ Experiment ─▶ Eval Runner
                                          ─▶ paired-bootstrap evidence ─▶ release gate
```

One backend operation, `evalops.promotion.promote_traces_to_dataset(session, *,
project_id, trace_ids, name)`. It builds one `Dataset` (version 1) and one
`DatasetCase` per trace, **in request order**, mapping
`trace.input → DatasetCase.input`, `trace.reference_output →
DatasetCase.expected_output`, `trace.id → DatasetCase.source_trace_id`, origin
`CaseOrigin.PROMOTED_TRACE`. `trace.output` is **never** used as ground truth:
a trace with no reference yields `expected_output=None` (the `DatasetCase`
model does not require one); if it ever did, the resulting
`DomainValidationError` propagates and the whole promotion rolls back — the
conflict is reported, not faked.

Validation: non-empty selection, no duplicate ids, every trace exists (→ 404),
every trace belongs to the project (→ 422). The `Dataset` + all cases are one
flush inside the caller's unit of work, so any failure is atomic and every
`ProductionTrace` row is left byte-for-byte unchanged (promotion is read-only
over traces). A repeated dataset name is a `RecordConflict` (409).

API: `POST /projects/{project_id}/trace-datasets` `{ "name", "trace_ids": [...] }`
→ **201** with the **normal `DatasetRead`** (cases carry `source_trace_id` and
`origin`). No trace-specific evaluation endpoint — the promoted dataset is
consumed by the same `POST /projects/{id}/experiments` + run path as any other.
No migration: `dataset_case.source_trace_id` and the `promoted_trace` origin
already exist (CP 8.1 / Phase 0).

### 7.3 Implemented: Production Traces dashboard + replay workflow (Phase 8, CP 8.3)

A *Production Traces* tab in the project workspace makes the whole loop
navigable — **production traffic → captured traces → select interactions →
replay dataset → baseline vs candidate → release decision** — with no new
evaluation semantics and no charts / observability dashboard.

* **Browse / select** — a trace list (captured time, resolved system version,
  input, output-or-error status, reference availability, latency, cost) with
  per-row checkboxes. Consumes `GET /projects/{id}/traces`.
* **Inspect** — a per-trace panel (input; *production output*, labelled
  explicitly as historical system output and **not** evaluation ground truth;
  optional reference; system version; metadata; latency / cost / error; trace id
  / origin). Consumes `GET /traces/{id}`.
* **Promote** — multi-select → a panel showing the selected count, live
  reference coverage ("_N of M selected traces have reference outputs_"), and a
  **non-blocking** warning when any lack references ("cases without references
  can still be replayed, but reference-based evaluators may not be
  applicable"). Calls `POST /projects/{id}/trace-datasets`. Production output is
  never offered as a reference.
* **Hand-off** — on success the panel links to the created dataset and into the
  **existing** experiment form, preselected via
  `/projects/{id}/experiments?dataset={id}` (the only change to that page: an
  optional `initialDatasetId`). From there the user is on the normal
  Dataset → Experiment → async run → statistical evidence → PASS/BLOCK path.
* **Add trace** — a small secondary form over `POST /projects/{id}/traces`,
  explicit fields only; the dashboard captures no headers, cookies, or
  environment.

Frontend only — the dashboard never re-derives a decision, and no backend,
gate, or schema code changed in this checkpoint.

### 7.4 Implemented: RAG evaluation foundation (Phase 9, CP 9.1)

**EvalOps evaluates retrieval behavior; it does not own the vector database or
the retrieval pipeline.** No embeddings, no vector store, no document
ingestion, no LangChain. An external RAG system reports what it retrieved;
EvalOps scores it through the *same* pipeline every other evaluator uses.

```
External RAG system
  -> provider execution result
       -> answer  (ProviderResponse.text)
       -> retrieval evidence  (ProviderResponse.retrieval: tuple[RetrievedItem])
  -> existing Eval Runner  (threads retrieval onto EvaluationRun.retrieval)
       -> retrieval / grounding evaluators  (ordinary Evaluator implementations)
  -> aggregation -> paired-bootstrap statistical evidence  (via <name>.pass_rate)
  -> existing release policy  (thresholds on <name>.pass_rate; unchanged gate)
```

**Retrieval evidence.** `RetrievedItem(doc_id, content, rank, score?)` — the
minimal, framework-neutral record. `ProviderResponse.retrieval` and
`EvaluationRun.retrieval` both default to `()`, so every text-only provider and
run is byte-identical to before. `MockProvider` reports deterministic evidence
from `parameters['mock']['retrieval']` (prompt → item list) /
`retrieval_default`. EvalOps performs no retrieval.

**Ground truth.** `DatasetCase.expected_retrieval_ids: tuple[str, ...]`
(default `()`), the relevant document/chunk ids. Every existing dataset and
every promoted-trace dataset stays valid with no labels.

**Evaluators** (all deterministic; each emits an ordinary `EvaluatorScore` with
the graded value in `score` and a threshold-derived `passed`, so
`<name>.pass_rate` flows through aggregation, evidence and the gate unchanged):

| type | metric | zero-denominator | default pass |
|---|---|---|---|
| `retrieval_recall` | `|relevant ∩ retrieved| / |relevant|` (unique ids) | no labels → `ConfigError` (never fabricated); nothing retrieved → `0.0` | `recall >= 1.0` |
| `context_precision` | `|relevant ∩ retrieved| / |retrieved|` (unique ids) | no labels → `ConfigError`; **nothing retrieved → `0.0`** (a retrieval failure, not perfect precision) | `precision >= 1.0` |
| `groundedness` → `groundedness_lexical` | `|answer_content_words ∩ context_content_words| / |answer_content_words|` | empty answer → `1.0` (vacuous); no context → `0.0` | `>= 0.8` |

`groundedness_lexical` is a **deterministic lexical approximation** of answer
support — it measures word overlap with the retrieved context, **not** semantic
truth or factual correctness, and is **not a hallucination detector**. The
result name carries the `_lexical` suffix and `LEXICAL_GROUNDEDNESS_NOTE`
states the limitation. A semantic groundedness *judge* would require extending
`LLMJudge` to take retrieval context as input — deliberately deferred so the
core metric stays deterministic and hosted-LLM-free.

**No RAG-specific machinery.** No RAG runner, experiment type, gate, or
statistics module. RAG metrics are `<name>.pass_rate` like any evaluator;
`gate._direction` already maps `*.pass_rate` to higher-is-better and
`expected_metric_names` already yields it. Continuous `score` values are
persisted on `evaluator_score.score` for inspection but are not aggregated —
pass-rate semantics were sufficient for CP 9.1 (see limitations in the CP
report for the graded-but-threshold-passing blind spot).

**Persistence / API (additive, one narrow migration `0e9c976c83ee`).**
`evaluation_run.retrieval` and `dataset_case.expected_retrieval_ids` are JSON
columns, `NOT NULL DEFAULT '[]'`, so a populated database backfills cleanly.
`EvaluationRunRead.retrieval` and `DatasetCaseRead.expected_retrieval_ids`
expose them through the existing run / dataset representations; no new
endpoints. `GET /results` recompute is unchanged — retrieval evidence is not
needed to reconstruct an `EvaluationResult`.

### 7.5 Implemented: agent / tool evaluation foundation (Phase 9, CP 9.2)

**EvalOps observes and evaluates tool behaviour; it does not execute arbitrary
external tools, plan, or judge semantic task correctness.** No agent framework,
no LangGraph/LangChain, no MCP, no memory.

```
External agent system
  -> provider execution result
       -> final output        (ProviderResponse.text)
       -> retrieval evidence  (optional, CP 9.1)
       -> tool-call evidence  (ProviderResponse.tool_calls: tuple[ToolCall])
  -> existing Eval Runner  (threads tool_calls onto EvaluationRun.tool_calls)
       -> agent evaluators  (ordinary Evaluator implementations)
  -> generic metric aggregation  (<name>.pass_rate AND <name>.mean_score)
  -> paired-bootstrap statistical evidence -> existing release policy -> PASS/BLOCK
```

**Tool-call evidence.** `ToolCall(name, arguments: Mapping, result: Any = None,
ok: bool = True, error: str | None = None)` — framework-neutral; tuple order is
the trajectory. `ProviderResponse.tool_calls` / `EvaluationRun.tool_calls`
default to `()`, so text-only and RAG-only executions are byte-identical to
before. `MockProvider` reports deterministic evidence from
`parameters['mock']['tool_calls']` (prompt → call list) / `tool_calls_default`.
EvalOps never executes a tool — `result` is whatever the external system
supplies.

**Ground truth.** `DatasetCase.expected_tool_calls: tuple[ExpectedToolCall,
...]` (default `()`), an *ordered* list of `ExpectedToolCall(name,
arguments: Mapping | None)`. `arguments is None` means "only the name is
expected here". Empty for every non-agent case and every promoted-trace case.

**Evaluators** (all `DETERMINISTIC`; each emits an ordinary `EvaluatorScore`):

| type | metric | key semantics | default pass |
|---|---|---|---|
| `tool_selection` | Jaccard of expected vs observed tool-name **sets** | order- and duplicate-independent; missing *and* extra tools lower it; no observed calls → `0.0`; no labels → `ConfigError` | `>= 1.0` |
| `tool_arguments` | fraction of arg-labelled expectations whose observed call matches **structurally** | canonical (key-order-independent, nested-aware) equality — missing/extra keys or a changed value fail; positional pairing for repeated tool names; **not** semantic equivalence; no arg labels → `ConfigError` | `>= 1.0` |
| `tool_success` | `successful observed calls / observed calls` | needs no labels; **zero observed calls → `1.0`** (no failure observed) | `>= 1.0` |
| `tool_trajectory` | sequence Dice: `2·LCS(expected, observed) / (len+len)` over the name sequences | **exact ordered adherence, not agent/task correctness**; sensitive to valid alternative orderings; no observed calls → `0.0`; no labels → `ConfigError` | `>= 1.0` |

**Generic `<evaluator>.mean_score` aggregation.** Revisiting the CP 9.1
limitation: `aggregate_results` now emits `<name>.mean_score` (the mean of
`EvaluatorScore.score`, failed runs contributing `0.0`) alongside
`<name>.pass_rate` **for every evaluator, not just RAG/agent**.
`build_statistical_evidence` produces continuous paired-bootstrap evidence for
it through the same path; `gate._direction` maps `.mean_score` to
higher-is-better; `expected_metric_names` yields it, so a `ReleasePolicy` can
threshold it with **no** RAG/agent-specific gate logic. This makes a graded
regression that stays above an evaluator's pass threshold (retrieval recall
1.0 → 0.9, tool selection 1.0 → 0.8) visible to the gate. `pass_rate` metrics
are unchanged. The additive metric is documented in §8.1 and the CP reports.

**Persistence / API (additive, one narrow migration `c09d84567ccc`).**
`evaluation_run.tool_calls` and `dataset_case.expected_tool_calls` are JSON
columns, `NOT NULL DEFAULT '[]'`. `EvaluationRunRead.tool_calls` and
`DatasetCaseRead.expected_tool_calls` expose them through the existing run /
dataset representations; no new endpoints; `GET /runs` faithfully reconstructs
an agent execution after a refresh.

### 7.6 Implemented: RAG + agent dashboard integration (Phase 9, CP 9.3)

The complete Phase 9 workflow is now navigable in the existing console — **no
new pages, no RAG/agent-specific experiment or result view, no metric computed
in the frontend**:

```
External AI system
  -> final answer
  -> retrieval evidence (optional)   ── captured by the provider execution result
  -> tool-call evidence  (optional)
  -> EvalOps evaluators  (chosen in the existing experiment run form)
  -> graded (mean_score) + pass-rate metrics
  -> paired statistical evidence     ── all backend-computed
  -> release gate                    ── existing ReleaseDecision component
```

* **Dataset UX** — the JSONL create form and parser accept the optional
  `expected_retrieval_ids` (RAG) and `expected_tool_calls` (agent, ordered
  `{name, arguments?}`) keys, with one-click example snippets for the three
  case shapes. Plain text-only cases are unchanged. Dataset detail shows the
  authored expectations per case behind progressive disclosure ("Retrieval
  expectations", "Tool expectations"), never overwhelming the input/reference.
* **Evaluator config** — the run form offers the shipped deterministic
  evaluators grouped Text / RAG / Agent, exposes exactly the backend
  thresholds (`min_recall` / `min_precision` / `min_groundedness` / `min_score`,
  blank = backend default), and flags which need authored labels. The backend
  stays authoritative — a label mismatch surfaces as its 422.
* **Run evidence** — each persisted run row expands to its evaluator scores
  and, only when present, a labelled **"Retrieved context"** (rank / id / score
  / content) and **"Tool trajectory"** (ordered name, ok/fail, arguments,
  result, error, shown as compact readable blocks, not a raw JSON dump).
  Text-only runs show only their scores. Copy states retrieval evidence is not
  ground truth and a tool trajectory does not prove task correctness.
* **Metrics + decision** — the existing `ReleaseDecision` renders the 14
  RAG/agent metric names with human-readable labels and a one-line legend
  distinguishing *pass rate* (fraction of checks meeting the threshold) from
  *mean score* (average graded score). Weak/inconclusive evidence semantics are
  untouched.

Production-trace replay datasets and every prior workflow are unaffected.

### 7.7 Implemented: dashboard UX foundation (Phase 10, CP 10.1)

A product-UX refactor of the dashboard shell only — **no backend, API,
persistence, or evaluation-semantics change**, and no deep redesign of the
experiment result/evidence views (that is CP 10.2).

* **Information architecture** — the crowded horizontally-scrolling project tab
  bar is replaced by a grouped, responsive project navigation
  (`ProjectNav`): **Overview** · **Evaluate** (Experiments, Datasets, System
  Versions) · **Production** (Production Traces) · **Configuration** (Release
  Policies) · **Advanced** (Judge Calibration). A sticky left sidebar on
  desktop, a collapsible section menu on narrow widths, no horizontal scroll.
  Every route is unchanged. The project name is the sidebar context header; the
  raw project UUID moves into a low-emphasis "Project details" disclosure.
* **Design system** — existing tokens are reused and extended (one added
  `--color-info` alias for the blue accent). A materially larger, non-uppercase
  type scale on the shared primitives (`PageHeader`, `Table`, form fields,
  `EmptyState`, `Steps`), a four-level button hierarchy
  (`primary` / `secondary` / `ghost` / `danger`, with `sm`/`md`/`lg` sizes),
  and light + dark themes both kept coherent.
* **Home / Help / Overview** — the Projects page leads with the hero *"Ship AI
  system changes with confidence."*, a **Create project** primary CTA and an
  inline 5-step *How EvalOps works*. A global **Help** drawer (accessible slide-
  over, Escape / backdrop close, focus managed) carries a plain-language
  glossary. The Project Overview is an actionable home: a real setup checklist
  (dataset → baseline/candidate → experiment → decision) and *Recent
  experiments* from data already fetched — **no project-level "latest decision"
  is fabricated** (there is no backend endpoint for it).
* **Feedback** — a minimal dependency-free toast (`ToastProvider` / `useToast`,
  `aria-live="polite"`) for resource-created confirmations only; persistent
  state (PASS/BLOCK, job progress) and field validation stay inline.

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
aggregation uses); `<evaluator>.mean_score` (CP 9.2) is the per-run
`EvaluatorScore.score`, continuous in [0, 1], `0.0` on a failed run, every
comparable pair contributing; `latency_ms.mean` drops any pair where either
side errored (a failed run has no meaningful latency, and the drop count is
recorded); `cost_usd.mean` keeps every pair (a failed call genuinely costs ~0).
Unmatched runs (a key on only one side — corrupt/partial data) are counted and
excluded.

**Additive metric `<evaluator>.mean_score` (CP 9.2).** `aggregate_results`
emits it for *every* evaluator alongside `<evaluator>.pass_rate` — the plain
arithmetic mean of `EvaluatorScore.score` (higher-is-better; failed runs count
as `0.0`). It exists so a *graded* regression that never crosses an evaluator's
own pass/fail threshold (retrieval recall 1.0 → 0.9, tool selection 1.0 → 0.8)
is still visible to a `ReleasePolicy`. It flows through the existing paired
bootstrap and gate with no new machinery: `_direction` treats `.mean_score`
as higher-is-better and nothing else changed. `pass_rate` metrics keep their
exact meaning.

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

**CLI / CI gate (CP 7.1).** `evalops run` routes through the same
`execution.run_evaluation(...)` orchestration the persisted/API path uses:
run → aggregate → attach paired-bootstrap `evidence` → statistically-aware
`evaluate_gate`. So the CLI release decision — `pass` /
`regression_low_evidence` / `regression_inconclusive` / `regression`,
`MIN_PAIRS_TO_BLOCK`, blocking reasons *and* advisories — is byte-for-byte the
same verdict a persisted run and the dashboard produce for equivalent data;
**CI cannot disagree with the dashboard.** The report gains a per-metric
`gate_outcome` and a top-level `advisories` list (`schema_version` bumped to 2);
the human report adds an "Advisories" section and an `ADVISORY` status marker.
Exit codes are unchanged and machine-safe for GitHub Actions: **0** = PASS
(including PASS with advisories), **1** = release BLOCK, **2** = any
config/execution/provider/judge error. No interactive prompts; nothing but the
report is written to stdout; a deterministic mock config is byte-identical
across runs.

**GitHub PR gate (CP 7.2, shipped).** `.github/workflows/release-gate.yml`
triggers on `pull_request` and `workflow_dispatch`. On `ubuntu-latest` /
Python 3.11 (uv + `uv sync --locked`, the repo's existing conventions) it:
runs `evalops run <deterministic mock config> --json <file> --quiet` capturing
the exit code without failing the step (`set +e`); always uploads the schema-v2
JSON as an artifact via `actions/upload-artifact` (`if-no-files-found: ignore`);
then `python -m evalops.ci --exit-code N --report <file> --log <stderr>` renders
`$GITHUB_STEP_SUMMARY` (PASS / BLOCK / ERROR heading, blocking reasons,
advisories, a compact metric table) and **exits with N verbatim** so the job
status *is* the gate. `evalops.ci` re-derives nothing — it only formats the
CLI's JSON, which came from the same shared `run_evaluation` path a local CI
run or the dashboard uses, and keeps exit 1 (BLOCK) and exit 2 (error) visually
and semantically distinct. PASS-with-advisories is a green PASS. No hosted
providers, no secrets, no bot comments / Checks API / commit-status calls —
GitHub's native workflow status is the check.

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
`POST /judge-calibrations` runs and persists one; `GET /judge-calibrations`
lists them (oldest first); `GET /judge-calibrations/{id}` retrieves one.

**Dashboard (CP 6.3).** A *Judge Calibration* tab in the project workspace
(the resource is global, like release policies). It runs a calibration from a
short human-labeled form and renders a persisted result: agreement rate,
scored / failed / total, the TP/TN/FP/FN matrix, precision / recall / F1, and a
per-example table of human verdict vs judge verdict with the judge's score and
reasoning. Failed judge calls are shown as a distinct row and undefined metrics
render as **N/A**. All numbers come from the API — the dashboard never
recomputes a metric — and the API key is only ever read from the server
environment. The copy states plainly that calibration does not affect release
gating.

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
| 7 | GitHub CI gate: PR-triggered `evalops run --json` workflow, PR step summary, non-zero exit on a real BLOCK | A deliberately bad candidate turns a GitHub Actions check red |
| 8 | Production trace feedback loop: trace ingestion, trace viewer, promote-to-regression, dataset versioning | A traced failure becomes a permanent regression case |
| 9 | RAG + agent evaluation, extending the existing evaluator abstraction (shipped: CP 9.1 RAG, CP 9.2 agent + generic `mean_score`, CP 9.3 dashboard) | No separate evaluation subsystem was built to support this |
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
/ci                 evalops.ci step-summary renderer + .github/workflows/release-gate.yml
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