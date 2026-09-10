"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime, shortId } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiments } from "@/lib/query/experiments";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { useSystemVersions } from "@/lib/query/system-versions";
import { ExperimentForm } from "./experiment-form";

export default function ExperimentsPage() {
  // useSearchParams() needs a Suspense boundary during prerender.
  return (
    <Suspense fallback={<LoadingState />}>
      <ExperimentsPageInner />
    </Suspense>
  );
}

function ExperimentsPageInner() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const router = useRouter();
  const searchParams = useSearchParams();

  // A promoted replay dataset (or any deep link) can preselect its dataset:
  // /projects/{id}/experiments?dataset={datasetId} opens the form on that dataset.
  const preselectedDatasetId = searchParams?.get("dataset") ?? "";

  const experiments = useExperiments(projectId);
  const [showForm, setShowForm] = useState(preselectedDatasetId !== "");

  const wantLabels = showForm || (experiments.data?.length ?? 0) > 0;
  const datasets = useDatasets(projectId, { enabled: wantLabels });
  const versions = useSystemVersions(projectId, { enabled: wantLabels });
  const policies = useReleasePolicies({ enabled: wantLabels });

  const datasetLabel = (id: string) =>
    datasets.data?.find((d) => d.id === id)?.name ?? shortId(id);
  const versionLabel = (id: string) => {
    const match = versions.data?.find((v) => v.id === id);
    return match ? `${match.name} ${match.version}` : shortId(id);
  };
  const policyLabel = (id: string | null) =>
    id === null
      ? "None"
      : (policies.data?.find((p) => p.id === id)?.name ?? shortId(id));

  const list = experiments.data ?? [];
  const base = `/projects/${projectId}/experiments`;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Experiments"
        description="Each experiment compares your current system against a candidate on one dataset, then runs the evaluation."
        actions={
          <Button
            variant={showForm ? "ghost" : "primary"}
            onClick={() => setShowForm((value) => !value)}
          >
            {showForm ? "Close" : "New experiment"}
          </Button>
        }
      />

      {showForm ? (
        <ExperimentForm
          projectId={projectId}
          initialDatasetId={preselectedDatasetId || undefined}
          onCreated={(experiment) => {
            setShowForm(false);
            router.push(`${base}/${experiment.id}`);
          }}
        />
      ) : null}

      {experiments.isPending ? (
        <LoadingState />
      ) : experiments.isError ? (
        <ErrorState
          title="Could not load experiments"
          message={apiErrorMessage(experiments.error, "The API did not respond.")}
          onRetry={() => void experiments.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No experiments yet"
          description="An experiment pairs a baseline system version with a candidate over a dataset."
          action={
            !showForm ? (
              <Button onClick={() => setShowForm(true)}>New experiment</Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH className="w-1/2">Comparison</TH>
              <TH>Dataset</TH>
              <TH>Policy</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {list.map((experiment) => (
              <TR key={experiment.id} className="relative hover:bg-surface-raised">
                <TD>
                  <Link
                    href={`${base}/${experiment.id}`}
                    className="font-medium text-fg after:absolute after:inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span>{versionLabel(experiment.baseline_version_id)}</span>
                    <span aria-hidden className="mx-1.5 text-fg-subtle">
                      →
                    </span>
                    <span className="text-accent">
                      {versionLabel(experiment.candidate_version_id)}
                    </span>
                  </Link>
                </TD>
                <TD className="text-fg-muted">
                  {datasetLabel(experiment.dataset_id)}
                </TD>
                <TD className="text-fg-muted">
                  {policyLabel(experiment.release_policy_id)}
                </TD>
                <TD className="whitespace-nowrap text-fg-muted">
                  {formatDateTime(experiment.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
