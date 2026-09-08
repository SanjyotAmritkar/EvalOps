"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createSystemVersion,
  getSystemVersion,
  listSystemVersions,
} from "@/lib/api/system-versions";
import type { SystemVersion, SystemVersionCreate } from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useSystemVersions(
  projectId: string,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.systemVersions.forProject(projectId),
    queryFn: () => listSystemVersions(projectId),
    enabled: projectId.length > 0 && (options?.enabled ?? true),
  });
}

export function useSystemVersion(id: string) {
  return useQuery({
    queryKey: queryKeys.systemVersions.detail(id),
    queryFn: () => getSystemVersion(id),
    enabled: id.length > 0,
  });
}

export function useCreateSystemVersion(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<SystemVersion, Error, SystemVersionCreate>({
    mutationFn: (body) => createSystemVersion(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.systemVersions.forProject(projectId),
      });
    },
  });
}
