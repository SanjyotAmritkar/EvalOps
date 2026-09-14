"use client";

import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createExperiment,
  getExperiment,
  getExperimentDiagnostics,
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

/**
 * Whether *any* experiment in `experimentIds` has at least one persisted
 * `EvaluationResult` — the authoritative "has this project run and reviewed a
 * release decision yet?" signal (Project Overview's Setup step 4). Fans the
 * same `GET /experiments/{id}/results` query {@link useExperimentResults}
 * uses out over every experiment (not just the recently-created few), so an
 * older experiment with a completed PASS / BLOCK / PASS-with-advisory result
 * counts identically — the check is only "a non-empty results array exists
 * somewhere", never which decision it holds. Shares the same query key, so a
 * page that already rendered a `DecisionBadge` for one of these ids reuses
 * its cached answer instead of refetching.
 *
 * `isPending` is true only while a query that hasn't answered yet is still
 * loading (not just "some query, somewhere, is refetching in the
 * background") -- callers should treat `hasCompletedResult` as `false` while
 * `isPending`, so a still-loading project never flashes "done". A rejected
 * query (network/API error) is likewise never a completed result — it is
 * treated the same as "no data found" from that experiment, not surfaced as
 * a page-level error.
 */
export function useProjectHasCompletedResult(experimentIds: string[]) {
  const results = useQueries({
    queries: experimentIds.map((id) => ({
      queryKey: queryKeys.experiments.results(id),
      queryFn: () => listExperimentResults(id),
    })),
  });

  const isPending = results.some((r) => r.isPending);
  const hasCompletedResult = results.some(
    (r) => r.status === "success" && r.data.length > 0,
  );

  return { isPending, hasCompletedResult };
}

/**
 * Case-level regression diagnostics for a completed experiment. Explanatory
 * only — it never carries a PASS/BLOCK decision. Invalidated on the same first
 * terminal job read as the runs / results queries.
 */
export function useExperimentDiagnostics(experimentId: string) {
  return useQuery({
    queryKey: queryKeys.experiments.diagnostics(experimentId),
    queryFn: () => getExperimentDiagnostics(experimentId),
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
      void queryClient.invalidateQueries({
        queryKey: queryKeys.experiments.diagnostics(experimentId),
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
        void queryClient.invalidateQueries({
          queryKey: queryKeys.experiments.diagnostics(experimentId),
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
