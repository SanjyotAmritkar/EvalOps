"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createJudgeCalibration,
  getJudgeCalibration,
  listJudgeCalibrations,
} from "@/lib/api/judge-calibrations";
import type {
  JudgeCalibration,
  JudgeCalibrationCreate,
} from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useJudgeCalibrations(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.judgeCalibrations.all,
    queryFn: listJudgeCalibrations,
    enabled: options?.enabled ?? true,
  });
}

export function useJudgeCalibration(id: string | null) {
  return useQuery({
    queryKey: queryKeys.judgeCalibrations.detail(id ?? "none"),
    queryFn: () => getJudgeCalibration(id as string),
    enabled: id !== null,
  });
}

export function useCreateJudgeCalibration() {
  const queryClient = useQueryClient();
  return useMutation<JudgeCalibration, Error, JudgeCalibrationCreate>({
    mutationFn: createJudgeCalibration,
    onSuccess: (created) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.judgeCalibrations.all,
      });
      // Seed the detail cache so the freshly created result renders without a
      // second round trip.
      queryClient.setQueryData(
        queryKeys.judgeCalibrations.detail(created.id),
        created,
      );
    },
  });
}
