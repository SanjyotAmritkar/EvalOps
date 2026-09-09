"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createExperiment,
  getExperiment,
  listExperimentResults,
  listExperimentRuns,
  listExperiments,
  runExperiment,
} from "@/lib/api/experiments";
import type {
  Experiment,
  ExperimentCreate,
  RunRequest,
  RunResponse,
} from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useExperiments(projectId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.forProject(projectId),
    queryFn: () => listExperiments(projectId),
    enabled: projectId.length > 0,
  });
}

export function useExperiment(experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.detail(experimentId),
    queryFn: () => getExperiment(experimentId),
    enabled: experimentId.length > 0,
  });
}

export function useExperimentRuns(experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.runs(experimentId),
    queryFn: () => listExperimentRuns(experimentId),
    enabled: experimentId.length > 0,
  });
}

export function useExperimentResults(experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.results(experimentId),
    queryFn: () => listExperimentResults(experimentId),
    enabled: experimentId.length > 0,
  });
}

export function useCreateExperiment(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation<Experiment, Error, ExperimentCreate>({
    mutationFn: (body) => createExperiment(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.experiments.forProject(projectId),
      });
    },
  });
}

export function useRunExperiment(experimentId: string) {
  const queryClient = useQueryClient();
  return useMutation<RunResponse, Error, RunRequest>({
    mutationFn: (body) => runExperiment(experimentId, body),
    onSettled: () => {
      // A 409 also means runs now exist; refresh history either way.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.experiments.runs(experimentId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.experiments.results(experimentId),
      });
    },
  });
}
