"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createExperiment,
  getExperiment,
  getJob,
  listExperimentResults,
  listExperimentRuns,
  listExperiments,
  runExperiment,
  runExperimentAsync,
} from "@/lib/api/experiments";
import type {
  AsyncJob,
  Experiment,
  ExperimentCreate,
  RunRequest,
  RunResponse,
} from "@/lib/api/types";
import { queryKeys } from "./keys";

/** How often to re-read a non-terminal job. Short-lived jobs, human-scale UI. */
export const JOB_POLL_INTERVAL_MS = 2000;

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

/**
 * Enqueue a background run. On success the caller holds the returned job id and
 * hands it to {@link useJob} to poll. A rejected enqueue (422 config, 500
 * broker dispatch) stays on this mutation's `error` — separate from a job that
 * is accepted and later fails.
 */
export function useRunExperimentAsync(experimentId: string) {
  return useMutation<AsyncJob, Error, RunRequest>({
    mutationFn: (body) => runExperimentAsync(experimentId, body),
  });
}

/**
 * Poll one background job until it reaches a terminal state. PostgreSQL is the
 * only source of truth. Polling stops on `completed` / `failed`; the interval
 * is disabled while `jobId` is null, and React Query tears the timer down when
 * the observer unmounts. On the first terminal read we invalidate the run /
 * result queries so the persisted decision refreshes itself.
 */
export function useJob(experimentId: string, jobId: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.jobs.detail(jobId ?? "none"),
    queryFn: async () => {
      const job = await getJob(jobId as string);
      if (job.status === "completed" || job.status === "failed") {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.experiments.runs(experimentId),
        });
        void queryClient.invalidateQueries({
          queryKey: queryKeys.experiments.results(experimentId),
        });
      }
      return job;
    },
    enabled: jobId !== null,
    // Re-read every tick until terminal, then stop. One in-flight request at a
    // time — React Query does not overlap refetches of the same query.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed"
        ? false
        : JOB_POLL_INTERVAL_MS;
    },
    refetchOnWindowFocus: false,
    staleTime: 0,
  });
}
