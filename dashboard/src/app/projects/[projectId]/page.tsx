"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { LinkButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import {
  DefinitionItem,
  DefinitionList,
} from "@/components/ui/definition-list";
import { formatDateTime } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiments } from "@/lib/query/experiments";
import { useProject } from "@/lib/query/projects";
import { useSystemVersions } from "@/lib/query/system-versions";

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
      className="group flex flex-col gap-1 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-fg-subtle/40 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
        {label}
      </span>
      <span className="text-2xl font-semibold tabular-nums text-fg">
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
  const nothingYet =
    (datasets.data?.length ?? 0) === 0 &&
    (systemVersions.data?.length ?? 0) === 0 &&
    (experiments.data?.length ?? 0) === 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description="Project identity and the resources defined so far. All counts come straight from the API."
        actions={
          <>
            <LinkButton variant="secondary" href={`${base}/datasets`}>
              Add dataset
            </LinkButton>
            <LinkButton variant="secondary" href={`${base}/system-versions`}>
              Add system version
            </LinkButton>
          </>
        }
      />

      <DefinitionList>
        <DefinitionItem term="Name">
          {project.data?.name ?? "…"}
        </DefinitionItem>
        <DefinitionItem term="Project ID">
          <span className="inline-flex items-center gap-2">
            <code className="font-mono text-xs text-fg-muted">
              {projectId}
            </code>
            <CopyButton value={projectId} />
          </span>
        </DefinitionItem>
        <DefinitionItem term="Created">
          {project.data ? formatDateTime(project.data.created_at) : "…"}
        </DefinitionItem>
      </DefinitionList>

      {nothingYet && !anyPending ? (
        <EmptyState
          title="No resources yet"
          description="Add a dataset of evaluation cases and at least one system version. Once both exist you can define an experiment."
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
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatTile
            label="Datasets"
            href={`${base}/datasets`}
            count={datasets.data?.length ?? 0}
            pending={datasets.isPending}
          />
          <StatTile
            label="System versions"
            href={`${base}/system-versions`}
            count={systemVersions.data?.length ?? 0}
            pending={systemVersions.isPending}
          />
          <StatTile
            label="Experiments"
            href={`${base}/experiments`}
            count={experiments.data?.length ?? 0}
            pending={experiments.isPending}
          />
        </div>
      )}
    </div>
  );
}
