import Link from "next/link";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/ui/copy-button";
import type {
  Dataset,
  Experiment,
  ReleasePolicy,
  SystemVersion,
} from "@/lib/api/types";
import { formatDateTime, shortId } from "@/lib/format";

function VersionSide({
  role,
  href,
  name,
}: {
  role: "baseline" | "candidate";
  href: string | null;
  name: string;
}) {
  const isCandidate = role === "candidate";
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-[13px] font-medium text-fg-subtle">
        {isCandidate ? "Candidate · proposed change" : "Baseline · current system"}
      </span>
      {href ? (
        <Link
          href={href}
          className={
            "truncate text-[19px] font-semibold tracking-tight transition-colors hover:text-accent " +
            (isCandidate ? "text-fg" : "text-fg")
          }
        >
          {name}
        </Link>
      ) : (
        <span className="truncate text-[19px] font-semibold tracking-tight text-fg">
          {name}
        </span>
      )}
    </div>
  );
}

/**
 * The comparison header for one experiment: baseline → candidate, the dataset
 * and case count, the release-policy status, and a primary action slot. Ids,
 * providers and config internals move into "Technical details". Project-level
 * context is not repeated here — the shell already shows it.
 */
export function ExperimentHeader({
  projectId,
  experiment,
  dataset,
  baseline,
  candidate,
  policy,
  action,
}: {
  projectId: string;
  experiment: Experiment;
  dataset?: Dataset;
  baseline?: SystemVersion;
  candidate?: SystemVersion;
  policy?: ReleasePolicy | null;
  action?: ReactNode;
}) {
  const base = `/projects/${projectId}`;
  const caseCount = dataset?.cases.length ?? null;
  const gated = experiment.release_policy_id !== null;

  return (
    <header className="flex flex-col gap-4">
      <span className="text-[13px] font-medium tracking-wide text-fg-muted">
        Experiment
      </span>

      <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="grid flex-1 items-center gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
          <VersionSide
            role="baseline"
            href={
              baseline ? `${base}/system-versions/${baseline.id}` : null
            }
            name={
              baseline
                ? `${baseline.name} ${baseline.version}`
                : shortId(experiment.baseline_version_id)
            }
          />
          <span
            aria-hidden
            className="text-fg-subtle sm:px-3 sm:text-xl"
          >
            <span className="sm:hidden">↓ compared against</span>
            <span className="hidden sm:inline">→</span>
          </span>
          <VersionSide
            role="candidate"
            href={
              candidate ? `${base}/system-versions/${candidate.id}` : null
            }
            name={
              candidate
                ? `${candidate.name} ${candidate.version}`
                : shortId(experiment.candidate_version_id)
            }
          />
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px] text-fg-muted">
        <span>
          Dataset:{" "}
          {dataset ? (
            <Link
              href={`${base}/datasets/${dataset.id}`}
              className="font-medium text-fg transition-colors hover:text-accent"
            >
              {dataset.name} v{dataset.version}
            </Link>
          ) : (
            <span className="font-mono text-[13px] text-fg-subtle">
              {shortId(experiment.dataset_id)}
            </span>
          )}
          {caseCount !== null
            ? ` · ${caseCount} case${caseCount === 1 ? "" : "s"}`
            : ""}
        </span>
        <span aria-hidden className="text-fg-subtle">
          ·
        </span>
        <span className="inline-flex items-center gap-1.5">
          Release policy:
          {gated ? (
            <Badge tone="info">{policy?.name ?? "attached"}</Badge>
          ) : (
            <Badge tone="neutral">none — comparison only</Badge>
          )}
        </span>
        <span aria-hidden className="text-fg-subtle">
          ·
        </span>
        <span>
          {experiment.repeats}× per case
        </span>
      </div>

      <details className="text-[13px] text-fg-subtle">
        <summary className="cursor-pointer font-medium text-fg-muted">
          Technical details
        </summary>
        <dl className="mt-3 flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Experiment ID</dt>
            <dd className="inline-flex items-center gap-2">
              <code className="font-mono">{experiment.id}</code>
              <CopyButton value={experiment.id} />
            </dd>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Dataset ID</dt>
            <dd>
              <code className="font-mono">{experiment.dataset_id}</code>
            </dd>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Baseline</dt>
            <dd>
              <code className="font-mono">
                {experiment.baseline_version_id}
              </code>
              {baseline ? ` · ${baseline.provider}/${baseline.model}` : ""}
            </dd>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Candidate</dt>
            <dd>
              <code className="font-mono">
                {experiment.candidate_version_id}
              </code>
              {candidate ? ` · ${candidate.provider}/${candidate.model}` : ""}
            </dd>
          </div>
          {experiment.release_policy_id ? (
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-32 shrink-0">Release policy ID</dt>
              <dd>
                <code className="font-mono">
                  {experiment.release_policy_id}
                </code>
              </dd>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Repeats</dt>
            <dd className="tabular-nums">{experiment.repeats}</dd>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <dt className="w-32 shrink-0">Created</dt>
            <dd>{formatDateTime(experiment.created_at)}</dd>
          </div>
        </dl>
      </details>
    </header>
  );
}
