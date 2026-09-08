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
