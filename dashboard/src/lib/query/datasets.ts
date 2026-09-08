"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDataset,
  getDataset,
  listDatasets,
} from "@/lib/api/datasets";
import type { Dataset, DatasetCreate } from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useDatasets(
  projectId: string,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.datasets.forProject(projectId),
    queryFn: () => listDatasets(projectId),
    enabled: projectId.length > 0 && (options?.enabled ?? true),
  });
}

export function useDataset(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.datasets.detail(datasetId),
    queryFn: () => getDataset(datasetId),
    enabled: datasetId.length > 0,
  });
}

export function useCreateDataset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<Dataset, Error, DatasetCreate>({
    mutationFn: (body) => createDataset(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.datasets.forProject(projectId),
      });
    },
  });
}
