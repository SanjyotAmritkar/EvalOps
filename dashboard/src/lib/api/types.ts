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

export interface DatasetCase {
  id: string;
  input: string;
  expected_output: string | null;
  origin: CaseOrigin;
  source_trace_id: string | null;
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
}

export interface DatasetCreate {
  name: string;
  version: number;
  cases: DatasetCaseInput[];
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

export type EvaluatorType = "exact_match" | "contains" | "regex_match";

export const EVALUATOR_TYPES: readonly EvaluatorType[] = [
  "exact_match",
  "contains",
  "regex_match",
];

export const OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434";
export const OLLAMA_DEFAULT_TIMEOUT_SECONDS = 120;

/** Mirrors the API's EvaluatorSpec (extra fields are rejected by the server). */
export interface EvaluatorSpec {
  type: EvaluatorType;
  name?: string;
  case_sensitive?: boolean;
  pattern?: string;
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

export interface EvaluationRun {
  id: string;
  system_version_id: string;
  case_id: string;
  repeat_index: number;
  output: string;
  error: string | null;
  usage: Usage;
  scores: EvaluatorScore[];
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
