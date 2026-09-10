import { apiFetch } from "./client";
import type {
  Dataset,
  ProductionTrace,
  TraceCreate,
  TraceDatasetCreate,
} from "./types";

export function listTraces(projectId: string): Promise<ProductionTrace[]> {
  return apiFetch<ProductionTrace[]>(`/projects/${projectId}/traces`);
}

export function getTrace(traceId: string): Promise<ProductionTrace> {
  return apiFetch<ProductionTrace>(`/traces/${traceId}`);
}

export function createTrace(
  projectId: string,
  body: TraceCreate,
): Promise<ProductionTrace> {
  return apiFetch<ProductionTrace>(`/projects/${projectId}/traces`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Promote selected production traces into one ordinary Dataset (CP 8.2). The
 * response is the normal Dataset — its cases carry `source_trace_id` provenance
 * and `origin: "promoted_trace"`. The source traces are not changed.
 */
export function createTraceDataset(
  projectId: string,
  body: TraceDatasetCreate,
): Promise<Dataset> {
  return apiFetch<Dataset>(`/projects/${projectId}/trace-datasets`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
