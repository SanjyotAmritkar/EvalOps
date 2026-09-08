"use client";

import { useQuery } from "@tanstack/react-query";
import { listExperiments } from "@/lib/api/experiments";
import { queryKeys } from "./keys";

export function useExperiments(projectId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.forProject(projectId),
    queryFn: () => listExperiments(projectId),
    enabled: projectId.length > 0,
  });
}
