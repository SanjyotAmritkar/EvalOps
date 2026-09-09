"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { LinkButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { WorkflowSteps } from "@/components/ui/workflow-steps";
import { formatDateTime } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiments } from "@/lib/query/experiments";
import { useProject } from "@/lib/query/projects";
import { useSystemVersions } from "@/lib/query/system-versions";

const SUMMARY =
  "EvalOps compares this project's current AI system against a candidate on the same evaluation dataset, measures quality, reliability, latency and cost, and applies a release policy to decide whether the candidate should ship.";

function StatTile({
  label,
  href,
  count,
  pending,
}: {
  label: string;
  href: string;
  count: number;
  pending: boolean;
}) {
  return (
    <Link
      href={href}
      className="group flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-fg-subtle/40 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="text-sm font-medium text-fg-muted">{label}</span>
      <span className="text-lg font-semibold tabular-nums text-fg">
        {pending ? "—" : count}
      </span>
    </Link>
  );
}

export default function ProjectOverviewPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");

  const project = useProject(projectId);
  const datasets = useDatasets(projectId);
  const systemVersions = useSystemVersions(projectId);
  const experiments = useExperiments(projectId);

  const base = `/projects/${projectId}`;
  const anyPending =
    datasets.isPending || systemVersions.isPending || experiments.isPending;
  const datasetCount = datasets.data?.length ?? 0;
  const versionCount = systemVersions.data?.length ?? 0;
  const experimentCount = experiments.data?.length ?? 0;
  const nothingYet =
    datasetCount === 0 && versionCount === 0 && experimentCount === 0;
  const readyToRun = datasetCount >= 1 && versionCount >= 2;

  const resourceActions = (
    <>
      <LinkButton variant="secondary" href={`${base}/datasets`}>
        Add dataset
      </LinkButton>
      <LinkButton variant="secondary" href={`${base}/system-versions`}>
        Add system version
      </LinkButton>
    </>
  );

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        description={SUMMARY}
        actions={
          readyToRun ? (
            <>
              <LinkButton href={`${base}/experiments`}>Run evaluation</LinkButton>
              {resourceActions}
            </>
          ) : (
            resourceActions
          )
        }
      />

      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5">
        <span className="text-[13px] font-medium text-fg-subtle">
          How this project is evaluated
        </span>
        <WorkflowSteps
          steps={[
            { label: "Evaluation data" },
            { label: "Baseline" },
            { label: "Candidate", tone: "candidate" },
            { label: "Release decision" },
          ]}
        />
        <p className="text-sm text-fg-muted">
          Each experiment runs the baseline and the candidate over one dataset,
          then the release policy turns the comparison into a PASS or BLOCK.
        </p>
      </div>

      {nothingYet && !anyPending ? (
        <EmptyState
          title="Nothing to evaluate yet"
          description="Add a dataset of evaluation cases and two system versions — your current configuration and a candidate. Then define an experiment and run it."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <LinkButton href={`${base}/datasets`}>New dataset</LinkButton>
              <LinkButton variant="secondary" href={`${base}/system-versions`}>
                New system version
              </LinkButton>
            </div>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-fg-subtle">
            Configured resources
          </span>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatTile
              label="Datasets"
              href={`${base}/datasets`}
              count={datasetCount}
              pending={datasets.isPending}
            />
            <StatTile
              label="System versions"
              href={`${base}/system-versions`}
              count={versionCount}
              pending={systemVersions.isPending}
            />
            <StatTile
              label="Experiments"
              href={`${base}/experiments`}
              count={experimentCount}
              pending={experiments.isPending}
            />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-fg-subtle">
        {project.data ? (
          <>
            <span>Created {formatDateTime(project.data.created_at)}</span>
            <span aria-hidden>·</span>
          </>
        ) : null}
        <code className="font-mono">{projectId}</code>
        <CopyButton value={projectId} label="Copy ID" />
      </div>
    </div>
  );
}
