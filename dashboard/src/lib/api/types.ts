/**
 * Hand-written mirrors of the FastAPI request/response schemas the dashboard
 * uses. Only the fields the console reads or sends. (Generation from the live
 * OpenAPI schema is still deferred; see the Phase 3 plan.)
 */

// --- Project ----------------------------------------------------------------

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
}

// --- Dataset --------------------------------------------------------------

export type CaseOrigin = "authored" | "promoted_trace";

/** Authored expected tool call (Phase 9, CP 9.2). `arguments === null` means
 * only the tool name is expected here. */
export interface ExpectedToolCall {
  name: string;
  arguments: Record<string, unknown> | null;
}

export interface ExpectedToolCallInput {
  name: string;
  arguments?: Record<string, unknown> | null;
}

export interface DatasetCase {
  id: string;
  input: string;
  expected_output: string | null;
  origin: CaseOrigin;
  source_trace_id: string | null;
  /** RAG ground truth (CP 9.1): relevant document/chunk ids. */
  expected_retrieval_ids: string[];
  /** Agent ground truth (CP 9.2): the expected ordered tool trajectory. */
  expected_tool_calls: ExpectedToolCall[];
}

export interface Dataset {
  id: string;
  project_id: string;
  name: string;
  version: number;
  created_at: string;
  cases: DatasetCase[];
}

export interface DatasetCaseInput {
  input: string;
  expected_output?: string;
  origin?: CaseOrigin;
  source_trace_id?: string;
  expected_retrieval_ids?: string[];
  expected_tool_calls?: ExpectedToolCallInput[];
}

export interface DatasetCreate {
  name: string;
  version: number;
  cases: DatasetCaseInput[];
}

// --- ProductionTrace (Phase 8) -----------------------------------------

export type TraceOrigin = "production";

/**
 * One real interaction captured from a running AI system (CP 8.1).
 * `output` is the historical system output — NOT evaluation ground truth.
 * `reference_output` is the optional known-good answer, if one was recorded.
 */
export interface ProductionTrace {
  id: string;
  project_id: string;
  system_version_id: string;
  created_at: string;
  input: string;
  output: string;
  reference_output: string | null;
  metadata: Record<string, unknown>;
  latency_ms: number | null;
  cost_usd: number | null;
  error: string | null;
  origin: TraceOrigin;
}

/** Body for POST /projects/{id}/traces. Only explicit, backend-supported fields. */
export interface TraceCreate {
  system_version_id: string;
  input: string;
  output?: string;
  reference_output?: string | null;
  metadata?: Record<string, unknown>;
  latency_ms?: number | null;
  cost_usd?: number | null;
  error?: string | null;
}

/** Body for POST /projects/{id}/trace-datasets (CP 8.2). Promotes traces, in
 * order, into one ordinary Dataset; the traces themselves are never mutated. */
export interface TraceDatasetCreate {
  name: string;
  trace_ids: string[];
}

// --- SystemVersion ------------------------------------------------------

export type ProviderName = "openai" | "anthropic" | "ollama";

export const PROVIDER_NAMES: readonly ProviderName[] = [
  "openai",
  "anthropic",
  "ollama",
];

export interface SystemVersion {
  id: string;
  project_id: string;
  name: string;
  version: string;
  provider: ProviderName;
  model: string;
  prompt_template: string;
  parameters: Record<string, unknown>;
  rag_config: Record<string, unknown> | null;
  tool_policy: Record<string, unknown> | null;
  created_at: string;
}

export interface SystemVersionCreate {
  name: string;
  version: string;
  provider: ProviderName;
  model: string;
  prompt_template: string;
  parameters?: Record<string, unknown>;
  rag_config?: Record<string, unknown> | null;
  tool_policy?: Record<string, unknown> | null;
}

// --- ReleasePolicy ----------------------------------------------------

export interface ReleasePolicy {
  id: string;
  name: string;
  thresholds: Record<string, number>;
  max_safety_violations: number;
}

export interface ReleasePolicyCreate {
  name: string;
  thresholds: Record<string, number>;
  max_safety_violations: number;
}

// --- Experiment ------------------------------------------------------

export interface Experiment {
  id: string;
  project_id: string;
  dataset_id: string;
  baseline_version_id: string;
  candidate_version_id: string;
  repeats: number;
  release_policy_id: string | null;
  created_at: string;
}

export interface ExperimentCreate {
  dataset_id: string;
  baseline_version_id: string;
  candidate_version_id: string;
  repeats: number;
  release_policy_id: string | null;
}

// --- running an experiment ------------------------------------------------

export type ExecutionBackend = "mock" | "ollama";

/** Deterministic evaluator types the backend ships (Phase 1 + CP 9.1 + CP 9.2).
 * `llm_judge` is configured elsewhere and is not offered by the run form. */
export type EvaluatorType =
  | "exact_match"
  | "contains"
  | "regex_match"
  | "retrieval_recall"
  | "context_precision"
  | "groundedness"
  | "tool_selection"
  | "tool_arguments"
  | "tool_success"
  | "tool_trajectory";

export const EVALUATOR_TYPES: readonly EvaluatorType[] = [
  "exact_match",
  "contains",
  "regex_match",
  "retrieval_recall",
  "context_precision",
  "groundedness",
  "tool_selection",
  "tool_arguments",
  "tool_success",
  "tool_trajectory",
];

export const OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434";
export const OLLAMA_DEFAULT_TIMEOUT_SECONDS = 120;

/** Mirrors the API's EvaluatorSpec (extra fields are rejected by the server). */
export interface EvaluatorSpec {
  type: EvaluatorType;
  name?: string;
  case_sensitive?: boolean;
  pattern?: string;
  // RAG evaluator pass thresholds (CP 9.1).
  min_recall?: number;
  min_precision?: number;
  min_groundedness?: number;
  // Agent evaluator pass threshold (CP 9.2).
  min_score?: number;
}

export interface ExecutionOptions {
  backend: ExecutionBackend;
  base_url?: string;
  timeout_seconds?: number;
}

export interface RunRequest {
  execution: ExecutionOptions;
  evaluators: EvaluatorSpec[];
}

/**
 * Per-metric gate outcome (CP 5.2). `regression` still drives BLOCK; this
 * distinguishes a blocking regression from a threshold breach the backend
 * held back because the statistical evidence was weak or inconclusive.
 * Optional: a response from an older API (or a stale cache) may omit it.
 */
export type GateOutcome =
  | "pass"
  | "regression"
  | "regression_inconclusive"
  | "regression_low_evidence";

export interface MetricLine {
  metric: string;
  baseline_value: number;
  candidate_value: number;
  delta: number;
  relative_delta: number | null;
  direction: string;
  threshold: number | null;
  adverse_change: number | null;
  regression: boolean;
  gate_outcome?: GateOutcome;
}

/** Mirrors the API's SampleSummaryRead. */
export interface SampleSummary {
  n: number;
  mean: number;
  median: number;
  stdev: number;
}

/**
 * Mirrors the API's MetricEvidenceRead (CP 5.2): the paired-bootstrap view of
 * one statistically supported metric. All values are backend-computed — the
 * dashboard only formats them, never re-derives a decision.
 */
export interface MetricEvidence {
  metric: string;
  kind: "binary" | "continuous";
  n_pairs: number;
  baseline: SampleSummary;
  candidate: SampleSummary;
  paired_delta: SampleSummary;
  delta: number;
  relative_change: number | null;
  confidence_level: number;
  ci_low: number | null;
  ci_high: number | null;
  ci_excludes_zero: boolean;
  insufficient_evidence: boolean;
  dropped_provider_failures: number;
  method: string;
}

/** The synchronous result of POST /experiments/{id}/run. */
export interface RunResponse {
  evaluation_result_id: string;
  experiment_id: string;
  dataset: string;
  baseline: string;
  candidate: string;
  repeats: number;
  counts: { cases: number; runs: number; failures: number };
  decision: string;
  gated: boolean;
  reasons: string[];
  metrics: MetricLine[];
  /** CP 5.2. Threshold breaches that did not BLOCK (weak/inconclusive evidence). */
  advisories?: string[];
  /** CP 5.2. One entry per statistically supported metric. */
  evidence?: MetricEvidence[];
}

// --- persisted run / result history ------------------------------------

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
}

export interface EvaluatorScore {
  evaluator: string;
  family: string;
  score: number;
  passed: boolean | null;
}

/** One document/chunk an external RAG system reported retrieving (CP 9.1). */
export interface RetrievedItem {
  doc_id: string;
  content: string;
  rank: number;
  score: number | null;
}

/** One tool invocation an external agent reported making (CP 9.2). */
export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  ok: boolean;
  error: string | null;
}

export interface EvaluationRun {
  id: string;
  system_version_id: string;
  case_id: string;
  repeat_index: number;
  output: string;
  error: string | null;
  usage: Usage;
  scores: EvaluatorScore[];
  /** RAG retrieval evidence, empty for text-only runs (CP 9.1). */
  retrieval: RetrievedItem[];
  /** Agent tool-call evidence, empty for non-agent runs (CP 9.2). */
  tool_calls: ToolCall[];
  created_at: string;
}

/**
 * A persisted EvaluationResult. `decision` / `gated` / `reasons` and the
 * per-metric verdict fields on each `MetricLine` are recomputed by the API on
 * read from the stored result + release policy (see the G-1 fix), so this
 * survives a page refresh and matches the original RunResponse.
 */
export interface EvaluationResult {
  id: string;
  experiment_id: string;
  created_at: string;
  decision: string;
  gated: boolean;
  reasons: string[];
  metrics: MetricLine[];
  /** CP 5.2. Recomputed on read alongside the decision, so it survives a refresh. */
  advisories?: string[];
  /** CP 5.2. Reconstructed from the persisted `metric_evidence` rows. */
  evidence?: MetricEvidence[];
}

// --- regression diagnostics (Phase 10, CP 10.2) ----------------------

/**
 * A candidate-side regression category. `evaluator_regression` is the generic
 * fallback for any evaluator that is not a known RAG / agent one. A future
 * backend may add categories, so treat this as open — {@link diagnosticCategory}
 * has a title-case fallback.
 */
export type RegressionCategory =
  | "evaluator_regression"
  | "provider_execution_failure"
  | "retrieval_regression"
  | "groundedness_regression"
  | "tool_selection_regression"
  | "tool_argument_regression"
  | "tool_execution_failure"
  | "trajectory_regression"
  | (string & {});

export interface DiagnosticCategoryCount {
  category: RegressionCategory;
  pairs: number;
  cases: number;
}

export interface DiagnosticEvaluatorCount {
  evaluator: string;
  pairs: number;
  cases: number;
  pass_to_fail: number;
  score_drop: number;
}

/** A pointer to one baseline/candidate run pair; ids resolve against GET /runs. */
export interface DiagnosticPairRef {
  repeat_index: number;
  baseline_run_id: string;
  candidate_run_id: string;
}

export interface RegressingCase {
  case_id: string;
  categories: RegressionCategory[];
  evaluators: string[];
  provider_failure: boolean;
  finding_count: number;
  representative: DiagnosticPairRef;
}

export interface DiagnosticFinding {
  case_id: string;
  repeat_index: number;
  baseline_run_id: string;
  candidate_run_id: string;
  category: RegressionCategory;
  kind: "provider_failure" | "evaluator_pass_to_fail" | "evaluator_score_drop";
  evaluator: string | null;
  baseline_detail: string;
  candidate_detail: string;
}

/**
 * Deterministic, explanatory-only case-level regression diagnostics
 * (GET /experiments/{id}/diagnostics). Every field is backend-computed from the
 * persisted runs; nothing here is a decision. `available` is false before the
 * first run.
 */
export interface RegressionDiagnostics {
  experiment_id: string;
  evaluation_result_id: string | null;
  baseline_version_id: string;
  candidate_version_id: string;
  matched_pairs: number;
  regressing_pairs: number;
  regressing_cases: number;
  available: boolean;
  categories: DiagnosticCategoryCount[];
  evaluators: DiagnosticEvaluatorCount[];
  cases: RegressingCase[];
  findings: DiagnosticFinding[];
}

// --- asynchronous execution job ---------------------------------------

/**
 * The durable lifecycle of a background experiment run. PostgreSQL is
 * authoritative — every field mirrors the `async_job` row, never Celery/Redis.
 * `queued` → `running` → `completed` | `failed` are the only transitions.
 */
export type AsyncJobStatus = "queued" | "running" | "completed" | "failed";

/** Mirrors the API's AsyncJobRead (GET /jobs/{id}, POST /experiments/{id}/run-async). */
export interface AsyncJob {
  id: string;
  experiment_id: string;
  status: AsyncJobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  evaluation_result_id: string | null;
  error: string | null;
  celery_task_id: string | null;
}

// --- LLM-judge calibration (Phase 6, CP 6.3) --------------------------

/** One human-labeled example sent to POST /judge-calibrations. */
export interface LabeledJudgeExampleInput {
  input: string;
  output: string;
  human_pass: boolean;
  reference?: string | null;
}

export interface JudgeCalibrationCreate {
  provider: ProviderName;
  model: string;
  name?: string;
  temperature?: number;
  base_url?: string;
  examples: LabeledJudgeExampleInput[];
}

/**
 * Aggregate judge-vs-human agreement (mirrors JudgeCalibrationMetricsRead).
 * Every value is backend-computed; a `null` ratio is an undefined metric
 * (zero denominator) and must render as "N/A", never 0. `scored` excludes
 * cases where the judge call failed.
 */
export interface JudgeCalibrationMetrics {
  total: number;
  scored: number;
  failures: number;
  agreements: number;
  agreement_rate: number | null;
  true_positives: number;
  true_negatives: number;
  false_positives: number;
  false_negatives: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

/** One labeled example after the judge scored it. `judge_pass === null` (with
 * `error` set) means the judge call failed and this case is excluded from the
 * metrics above. */
export interface JudgeCalibrationCase {
  input: string;
  output: string;
  reference: string | null;
  human_pass: boolean;
  judge_pass: boolean | null;
  judge_score: number | null;
  judge_reasoning: string | null;
  error: string | null;
}

/** Mirrors JudgeCalibrationRead (GET/POST /judge-calibrations). */
export interface JudgeCalibration {
  id: string;
  created_at: string;
  judge_provider: ProviderName;
  judge_model: string;
  judge_name: string;
  judge_temperature: number;
  rubric_id: string;
  metrics: JudgeCalibrationMetrics;
  cases: JudgeCalibrationCase[];
}
