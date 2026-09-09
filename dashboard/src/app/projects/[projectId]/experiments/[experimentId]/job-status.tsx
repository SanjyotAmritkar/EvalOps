"use client";

import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { apiErrorMessage } from "@/lib/api/errors";
import type { AsyncJobStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { useExperimentResults, useJob } from "@/lib/query/experiments";
import { ReleaseDecision } from "./release-decision";

type Tone = "pending" | "active" | "done" | "error";

const LIFECYCLE: Record<
  AsyncJobStatus,
  { label: string; detail: string; tone: Tone }
> = {
  queued: {
    label: "Queued",
    detail: "waiting for a worker",
    tone: "pending",
  },
  running: {
    label: "Running",
    detail: "evaluation in progress",
    tone: "active",
  },
  completed: {
    label: "Completed",
    detail: "the background run finished",
    tone: "done",
  },
  failed: {
    label: "Failed",
    detail: "the background run did not finish",
    tone: "error",
  },
};

const DOT_TONE: Record<Tone, string> = {
  pending: "bg-fg-subtle",
  active: "bg-accent animate-pulse",
  done: "bg-pass",
  error: "bg-block",
};

function Lifecycle({ status }: { status: AsyncJobStatus }) {
  const meta = LIFECYCLE[status];
  return (
    <div
      className="flex flex-wrap items-center gap-2.5"
      role="status"
      aria-live="polite"
    >
      <span
        className={cn("h-2 w-2 shrink-0 rounded-full", DOT_TONE[meta.tone])}
        aria-hidden
      />
      <span className="text-sm font-medium text-fg">{meta.label}</span>
      <span className="text-sm text-fg-muted">— {meta.detail}</span>
    </div>
  );
}

/**
 * The live view of a background run the dashboard just enqueued. It polls the
 * PostgreSQL-backed job (via {@link useJob}) and shows a compact lifecycle:
 * Queued / Running / Completed / Failed. A gated BLOCK arrives here as a
 * *completed* run and is rendered by <ReleaseDecision>, never as a failure.
 */
export function JobStatus({
  experimentId,
  jobId,
  onReset,
}: {
  experimentId: string;
  jobId: string;
  onReset: () => void;
}) {
  const job = useJob(experimentId, jobId);
  const results = useExperimentResults(experimentId);

  if (job.isPending) {
    return (
      <p className="text-sm text-fg-subtle" role="status">
        Reading job status…
      </p>
    );
  }

  if (job.isError || !job.data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-block">
          {apiErrorMessage(
            job.error,
            "Could not read the background job status.",
          )}
        </p>
        <Button variant="secondary" onClick={onReset}>
          Back to run configuration
        </Button>
      </div>
    );
  }

  const data = job.data;

  if (data.status === "failed") {
    return (
      <div className="flex flex-col items-start gap-4">
        <Lifecycle status="failed" />
        <div className="w-full rounded-md border border-block/30 bg-surface px-3 py-2.5">
          <p className="text-sm font-medium text-block">
            The evaluation run failed on the worker.
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-fg-muted">
            {data.error ?? "No error detail was recorded for this job."}
          </p>
        </div>
        <Button variant="secondary" onClick={onReset}>
          Try running again
        </Button>
      </div>
    );
  }

  if (data.status === "completed") {
    const result =
      results.data?.find((r) => r.id === data.evaluation_result_id) ??
      results.data?.[results.data.length - 1];

    return (
      <div className="flex flex-col gap-4">
        <Lifecycle status="completed" />
        {result ? (
          <ReleaseDecision
            decision={result.decision}
            gated={result.gated}
            reasons={result.reasons}
            metrics={result.metrics}
            resultId={result.id}
            advisories={result.advisories}
            evidence={result.evidence}
          />
        ) : results.isFetching ? (
          <p className="text-sm text-fg-subtle">Loading the stored result…</p>
        ) : (
          <p className="text-sm text-fg-muted">
            The run finished, but no stored evaluation result was found.
          </p>
        )}
      </div>
    );
  }

  // queued / running
  return (
    <div className="flex flex-col gap-3">
      <Lifecycle status={data.status} />
      <p className="text-xs text-fg-subtle">
        Runs on a background worker — you can leave this page and come back.
      </p>
      <span className="inline-flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
        <span>Job</span>
        <code className="font-mono text-fg-muted">{data.id}</code>
        <CopyButton value={data.id} />
      </span>
    </div>
  );
}
