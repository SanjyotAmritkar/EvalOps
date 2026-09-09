import { apiFetch } from "./client";
import type {
  AsyncJob,
  EvaluationResult,
  EvaluationRun,
  Experiment,
  ExperimentCreate,
  RunRequest,
  RunResponse,
} from "./types";

export function listExperiments(projectId: string): Promise<Experiment[]> {
  return apiFetch<Experiment[]>(`/projects/${projectId}/experiments`);
}

export function getExperiment(experimentId: string): Promise<Experiment> {
  return apiFetch<Experiment>(`/experiments/${experimentId}`);
}

export function createExperiment(
  projectId: string,
  body: ExperimentCreate,
): Promise<Experiment> {
  return apiFetch<Experiment>(`/projects/${projectId}/experiments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function runExperiment(
  experimentId: string,
  body: RunRequest,
): Promise<RunResponse> {
  return apiFetch<RunResponse>(`/experiments/${experimentId}/run`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Queue a background run. Returns HTTP 202 with the freshly created `queued`
 * job. Structural request problems come back as 422 here; a broker dispatch
 * failure as 500. Everything else (a bad evaluator config, a provider error)
 * surfaces later as a `failed` job from {@link getJob}.
 */
export function runExperimentAsync(
  experimentId: string,
  body: RunRequest,
): Promise<AsyncJob> {
  return apiFetch<AsyncJob>(`/experiments/${experimentId}/run-async`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Read the PostgreSQL-backed status of a background run. */
export function getJob(jobId: string): Promise<AsyncJob> {
  return apiFetch<AsyncJob>(`/jobs/${jobId}`);
}

export function listExperimentRuns(
  experimentId: string,
): Promise<EvaluationRun[]> {
  return apiFetch<EvaluationRun[]>(`/experiments/${experimentId}/runs`);
}

export function listExperimentResults(
  experimentId: string,
): Promise<EvaluationResult[]> {
  return apiFetch<EvaluationResult[]>(`/experiments/${experimentId}/results`);
}
