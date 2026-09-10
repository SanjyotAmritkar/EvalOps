"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { LinkButton } from "@/components/ui/button";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { BackLink } from "@/components/layout/back-link";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import { describeThreshold, metricLabel } from "@/lib/metric-labels";
import { useDatasets } from "@/lib/query/datasets";
import {
  useExperiment,
  useExperimentDiagnostics,
  useExperimentResults,
  useExperimentRuns,
} from "@/lib/query/experiments";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { useSystemVersions } from "@/lib/query/system-versions";
import { ExperimentHeader } from "./experiment-header";
import { JobStatus } from "./job-status";
import { PersistedHistory } from "./persisted-history";
import { ResultPanel } from "./result-panel";
import { RunForm } from "./run-form";

const DECISION_LABEL: Record<string, string> = {
  pass: "PASS",
  block: "BLOCK",
};

export default function ExperimentDetailPage() {
  const params = useParams<{ projectId: string; experimentId: string }>();
  const projectId = String(params.projectId ?? "");
  const experimentId = String(params.experimentId ?? "");

  const experiment = useExperiment(experimentId);
  const datasets = useDatasets(projectId);
  const versions = useSystemVersions(projectId);
  const policies = useReleasePolicies();
  const runs = useExperimentRuns(experimentId);
  const results = useExperimentResults(experimentId);
  const diagnostics = useExperimentDiagnostics(experimentId);

  // The id of the background run enqueued from this page, if any.
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const backHref = `/projects/${projectId}/experiments`;

  if (experiment.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <BackLink href={backHref} label="Experiments" />
        <LoadingState rows={5} />
      </div>
    );
  }

  if (experiment.isError || !experiment.data) {
    const notFound = isNotFound(experiment.error);
    return (
      <div className="flex flex-col gap-4">
        <BackLink href={backHref} label="Experiments" />
        <ErrorState
          title={notFound ? "Experiment not found" : "Could not load experiment"}
          message={
            notFound
              ? "This experiment does not exist."
              : apiErrorMessage(experiment.error, "The API did not respond.")
          }
          onRetry={notFound ? undefined : () => void experiment.refetch()}
        />
      </div>
    );
  }

  const exp = experiment.data;
  const dataset = datasets.data?.find((d) => d.id === exp.dataset_id);
  const baseline = versions.data?.find((v) => v.id === exp.baseline_version_id);
  const candidate = versions.data?.find((v) => v.id === exp.candidate_version_id);
  const policy =
    exp.release_policy_id === null
      ? null
      : policies.data?.find((p) => p.id === exp.release_policy_id);

  const runList = runs.data ?? [];
  const persistedResult = results.data?.[results.data.length - 1];
  const checkingRunState = runs.isPending || results.isPending;
  const thresholds = policy ? Object.entries(policy.thresholds) : [];
  const policyHref = `/projects/${projectId}/release-policies`;

  const showRunCta =
    !activeJobId &&
    !checkingRunState &&
    !persistedResult &&
    runList.length === 0;

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-6">
        <BackLink href={backHref} label="Experiments" />
        <ExperimentHeader
          projectId={projectId}
          experiment={exp}
          dataset={dataset}
          baseline={baseline}
          candidate={candidate}
          policy={policy}
          action={
            showRunCta ? (
              <LinkButton href="#run" size="lg">
                Run evaluation
              </LinkButton>
            ) : undefined
          }
        />
      </div>

      <section id="run" className="flex flex-col gap-4">
        {activeJobId ? (
          <>
            <h2 className="text-lg font-semibold text-fg">Background run</h2>
            <JobStatus
              experimentId={experimentId}
              jobId={activeJobId}
              onReset={() => setActiveJobId(null)}
            />
          </>
        ) : checkingRunState ? (
          <p className="text-sm text-fg-subtle">Checking run status…</p>
        ) : persistedResult ? (
          <div className="flex flex-col gap-3">
            <p className="text-[13px] text-fg-subtle">
              Decision recomputed from stored results — it survives a refresh.
            </p>
            <ResultPanel
              result={persistedResult}
              diagnostics={diagnostics.data}
              runs={runList}
              datasetCases={dataset?.cases}
              policyHref={policyHref}
            />
          </div>
        ) : runList.length > 0 ? (
          <>
            <h2 className="text-lg font-semibold text-fg">Run evaluation</h2>
            <p className="text-sm text-fg-muted">
              This experiment has been run, but no evaluation result is stored.
              Run records appear under Run history below.
            </p>
          </>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-fg">Run evaluation</h2>
            <RunForm
              experimentId={experimentId}
              onEnqueued={(job) => setActiveJobId(job.id)}
            />
          </>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-fg">Release policy</h2>
        {exp.release_policy_id === null ? (
          <p className="text-sm text-fg-muted">
            No release policy is attached. A run compares the two versions but
            produces no PASS / BLOCK decision.
          </p>
        ) : (
          <>
            <p className="text-sm text-fg-muted">
              <span className="font-medium text-fg">
                {policy?.name ?? "This policy"}
              </span>{" "}
              — the candidate passes only if each metric stays within its allowed
              regression.
            </p>
            {thresholds.length > 0 ? (
              <ul className="flex flex-col rounded-lg border border-border">
                {thresholds.map(([metric, value]) => (
                  <li
                    key={metric}
                    className="flex flex-wrap items-center justify-between gap-x-4 gap-y-0.5 border-b border-border px-4 py-2.5 last:border-b-0"
                  >
                    <span className="flex flex-col">
                      <span className="text-sm font-medium text-fg">
                        {metricLabel(metric)}
                      </span>
                      <span className="font-mono text-[12px] text-fg-subtle">
                        {metric}
                      </span>
                    </span>
                    <span className="text-sm text-fg-muted">
                      {describeThreshold(value)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-fg-subtle">
                This policy defines no metric thresholds.
              </p>
            )}
          </>
        )}
      </section>

      {persistedResult || runList.length > 0 ? (
        <PersistedHistory
          experimentId={experimentId}
          baseline={baseline}
          candidate={candidate}
          resultCreatedAt={persistedResult?.created_at}
          decisionLabel={
            persistedResult && persistedResult.gated
              ? (DECISION_LABEL[persistedResult.decision] ??
                persistedResult.decision)
              : persistedResult
                ? "comparison only"
                : undefined
          }
        />
      ) : null}
    </div>
  );
}
