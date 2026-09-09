"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { BackLink } from "@/components/layout/back-link";
import { CopyButton } from "@/components/ui/copy-button";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import type { RunResponse } from "@/lib/api/types";
import { formatDateTime, shortId } from "@/lib/format";
import { describeThreshold, metricLabel } from "@/lib/metric-labels";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiment, useExperimentRuns } from "@/lib/query/experiments";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { useSystemVersions } from "@/lib/query/system-versions";
import { PersistedHistory } from "./persisted-history";
import { RunForm } from "./run-form";
import { RunSummary } from "./run-summary";

function VersionSide({
  kind,
  href,
  name,
}: {
  kind: "baseline" | "candidate";
  href: string | null;
  name: string;
}) {
  const isCandidate = kind === "candidate";
  return (
    <div
      className={
        isCandidate
          ? "-m-1 flex flex-col gap-1 rounded-md bg-accent/5 p-1 sm:-m-2 sm:p-2"
          : "flex flex-col gap-1"
      }
    >
      <span
        className={
          isCandidate
            ? "text-[11px] font-semibold uppercase tracking-wider text-accent"
            : "text-[11px] font-semibold uppercase tracking-wider text-fg-subtle"
        }
      >
        {isCandidate ? "Candidate · proposed change" : "Baseline · current system"}
      </span>
      {href ? (
        <Link
          href={href}
          className="text-xl font-semibold text-fg transition-colors hover:text-accent"
        >
          {name}
        </Link>
      ) : (
        <span className="text-xl font-semibold text-fg">{name}</span>
      )}
    </div>
  );
}

export default function ExperimentDetailPage() {
  const params = useParams<{ projectId: string; experimentId: string }>();
  const projectId = String(params.projectId ?? "");
  const experimentId = String(params.experimentId ?? "");

  const experiment = useExperiment(experimentId);
  const datasets = useDatasets(projectId);
  const versions = useSystemVersions(projectId);
  const policies = useReleasePolicies();
  const runs = useExperimentRuns(experimentId);

  const [justRan, setJustRan] = useState<RunResponse | null>(null);

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
  const candidate = versions.data?.find(
    (v) => v.id === exp.candidate_version_id,
  );
  const policy =
    exp.release_policy_id === null
      ? null
      : policies.data?.find((p) => p.id === exp.release_policy_id);

  const alreadyRun = (runs.data?.length ?? 0) > 0;
  const thresholds = policy ? Object.entries(policy.thresholds) : [];

  return (
    <div className="flex flex-col gap-9">
      <div className="flex flex-col gap-4">
        <BackLink href={backHref} label="Experiments" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          Experiment
        </span>

        <div className="grid gap-3 rounded-lg border border-border bg-surface p-5 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
          <VersionSide
            kind="baseline"
            href={
              baseline
                ? `/projects/${projectId}/system-versions/${baseline.id}`
                : null
            }
            name={
              baseline
                ? `${baseline.name} ${baseline.version}`
                : shortId(exp.baseline_version_id)
            }
          />
          <span
            aria-hidden
            className="justify-self-start text-sm font-medium text-fg-subtle sm:justify-self-center sm:text-2xl"
          >
            <span className="sm:hidden">↓ compared against</span>
            <span className="hidden sm:inline">→</span>
          </span>
          <VersionSide
            kind="candidate"
            href={
              candidate
                ? `/projects/${projectId}/system-versions/${candidate.id}`
                : null
            }
            name={
              candidate
                ? `${candidate.name} ${candidate.version}`
                : shortId(exp.candidate_version_id)
            }
          />
        </div>

        <p className="text-[15px] leading-relaxed text-fg-muted">
          Dataset:{" "}
          {dataset ? (
            <Link
              href={`/projects/${projectId}/datasets/${dataset.id}`}
              className="font-medium text-fg transition-colors hover:text-accent"
            >
              {dataset.name} v{dataset.version}
            </Link>
          ) : (
            <span className="font-mono text-[13px] text-fg-subtle">
              {shortId(exp.dataset_id)}
            </span>
          )}
          {dataset
            ? ` · ${dataset.cases.length} evaluation case${dataset.cases.length === 1 ? "" : "s"}`
            : ""}
          {" · "}Release policy:{" "}
          {exp.release_policy_id === null ? (
            <span className="text-fg-subtle">none</span>
          ) : (
            <span className="font-medium text-fg">
              {policy?.name ?? "policy"}
            </span>
          )}
        </p>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-fg">Run evaluation</h2>
        {justRan ? (
          <RunSummary result={justRan} />
        ) : runs.isPending ? (
          <p className="text-sm text-fg-subtle">Checking run status…</p>
        ) : alreadyRun ? (
          <p className="text-sm text-fg-muted">
            This experiment has already been run. Its runs and results are
            immutable and appear under Technical details below.
          </p>
        ) : (
          <RunForm experimentId={experimentId} onCompleted={setJustRan} />
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
                      <span className="font-mono text-[11px] text-fg-subtle">
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
        <p className="text-[13px] text-fg-subtle">
          Each evaluation case runs {exp.repeats}× per version.
        </p>
      </section>

      <details className="border-t border-border pt-6">
        <summary className="cursor-pointer text-sm font-semibold text-fg-muted">
          Technical details
        </summary>
        <div className="mt-4 flex flex-col gap-6">
          <dl className="flex flex-col gap-1.5 text-[13px] text-fg-subtle">
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Experiment ID</dt>
              <dd className="inline-flex items-center gap-2">
                <code className="font-mono">{exp.id}</code>
                <CopyButton value={exp.id} />
              </dd>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Dataset ID</dt>
              <dd>
                <code className="font-mono">{exp.dataset_id}</code>
              </dd>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Baseline</dt>
              <dd>
                <code className="font-mono">{exp.baseline_version_id}</code>
                {baseline ? ` · ${baseline.provider}/${baseline.model}` : ""}
              </dd>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Candidate</dt>
              <dd>
                <code className="font-mono">{exp.candidate_version_id}</code>
                {candidate ? ` · ${candidate.provider}/${candidate.model}` : ""}
              </dd>
            </div>
            {exp.release_policy_id ? (
              <div className="flex flex-wrap items-center gap-2">
                <dt className="w-28 shrink-0">Release policy ID</dt>
                <dd>
                  <code className="font-mono">{exp.release_policy_id}</code>
                </dd>
              </div>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Repeats</dt>
              <dd className="tabular-nums">{exp.repeats}</dd>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0">Created</dt>
              <dd>{formatDateTime(exp.created_at)}</dd>
            </div>
          </dl>

          <PersistedHistory
            experimentId={experimentId}
            baseline={baseline}
            candidate={candidate}
          />
        </div>
      </details>
    </div>
  );
}
