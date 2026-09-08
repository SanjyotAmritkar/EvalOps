"use client";

import { useParams } from "next/navigation";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime, shortId } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiments } from "@/lib/query/experiments";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { useSystemVersions } from "@/lib/query/system-versions";

export default function ExperimentsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");

  const experiments = useExperiments(projectId);
  // Resolve the id references to human labels only once there are rows to label.
  const hasRows = (experiments.data?.length ?? 0) > 0;
  const datasets = useDatasets(projectId, { enabled: hasRows });
  const versions = useSystemVersions(projectId, { enabled: hasRows });
  const policies = useReleasePolicies({ enabled: hasRows });

  const datasetLabel = (id: string) =>
    datasets.data?.find((d) => d.id === id)?.name ?? shortId(id);
  const versionLabel = (id: string) => {
    const match = versions.data?.find((v) => v.id === id);
    return match ? `${match.name} ${match.version}` : shortId(id);
  };
  const policyLabel = (id: string | null) =>
    id === null
      ? "—"
      : (policies.data?.find((p) => p.id === id)?.name ?? shortId(id));

  const list = experiments.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Experiments"
        description="Baseline-vs-candidate comparisons defined for this project."
      />

      {experiments.isPending ? (
        <LoadingState />
      ) : experiments.isError ? (
        <ErrorState
          title="Could not load experiments"
          message={apiErrorMessage(
            experiments.error,
            "The API did not respond.",
          )}
          onRetry={() => void experiments.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No experiments yet"
          description="An experiment pairs a baseline system version with a candidate over a dataset. Creating and running experiments arrives in a later update."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Dataset</TH>
              <TH>Baseline</TH>
              <TH>Candidate</TH>
              <TH>Repeats</TH>
              <TH>Policy</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {list.map((experiment) => (
              <TR key={experiment.id}>
                <TD>{datasetLabel(experiment.dataset_id)}</TD>
                <TD>{versionLabel(experiment.baseline_version_id)}</TD>
                <TD>{versionLabel(experiment.candidate_version_id)}</TD>
                <TD className="tabular-nums text-fg-muted">
                  {experiment.repeats}
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
