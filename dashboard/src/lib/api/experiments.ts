import { apiFetch } from "./client";
import type { Experiment } from "./types";

export function listExperiments(projectId: string): Promise<Experiment[]> {
  return apiFetch<Experiment[]>(`/projects/${projectId}/experiments`);
}
