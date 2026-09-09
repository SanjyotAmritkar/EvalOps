import { apiFetch } from "./client";
import type {
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
