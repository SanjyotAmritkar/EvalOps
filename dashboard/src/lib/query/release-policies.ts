"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createReleasePolicy,
  listReleasePolicies,
} from "@/lib/api/release-policies";
import type { ReleasePolicy, ReleasePolicyCreate } from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useReleasePolicies(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.releasePolicies.all,
    queryFn: listReleasePolicies,
    enabled: options?.enabled ?? true,
  });
}

export function useCreateReleasePolicy() {
  const queryClient = useQueryClient();
  return useMutation<ReleasePolicy, Error, ReleasePolicyCreate>({
    mutationFn: createReleasePolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.releasePolicies.all,
      });
    },
  });
}
