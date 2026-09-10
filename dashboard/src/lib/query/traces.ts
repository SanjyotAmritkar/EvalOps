"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createTrace,
  createTraceDataset,
  getTrace,
  listTraces,
} from "@/lib/api/traces";
import type {
  Dataset,
  ProductionTrace,
  TraceCreate,
  TraceDatasetCreate,
} from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useTraces(projectId: string) {
  return useQuery({
    queryKey: queryKeys.traces.forProject(projectId),
    queryFn: () => listTraces(projectId),
    enabled: projectId.length > 0,
  });
}

export function useTrace(traceId: string | null) {
  return useQuery({
    queryKey: queryKeys.traces.detail(traceId ?? "none"),
    queryFn: () => getTrace(traceId as string),
    enabled: traceId !== null && traceId.length > 0,
  });
}

export function useCreateTrace(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<ProductionTrace, Error, TraceCreate>({
    mutationFn: (body) => createTrace(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.traces.forProject(projectId),
      });
    },
  });
}

/**
 * Promote traces into a replay Dataset. On success the datasets list is
 * refreshed so the new dataset shows up under the Datasets tab immediately.
 */
export function useCreateTraceDataset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<Dataset, Error, TraceDatasetCreate>({
    mutationFn: (body) => createTraceDataset(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.datasets.forProject(projectId),
      });
    },
  });
}
