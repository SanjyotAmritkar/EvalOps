import { apiFetch } from "./client";
import type { Dataset, DatasetCreate } from "./types";

export function listDatasets(projectId: string): Promise<Dataset[]> {
  return apiFetch<Dataset[]>(`/projects/${projectId}/datasets`);
}

export function getDataset(datasetId: string): Promise<Dataset> {
  return apiFetch<Dataset>(`/datasets/${datasetId}`);
}

export function createDataset(
  projectId: string,
  body: DatasetCreate,
): Promise<Dataset> {
  return apiFetch<Dataset>(`/projects/${projectId}/datasets`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
