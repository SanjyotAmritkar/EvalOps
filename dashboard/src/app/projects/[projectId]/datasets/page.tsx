"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { DatasetForm } from "./dataset-form";

export default function DatasetsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const datasets = useDatasets(projectId);
  const [showForm, setShowForm] = useState(false);

  const list = datasets.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Datasets"
        description="Versioned, immutable collections of evaluation cases."
        actions={
          <Button onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "New dataset"}
          </Button>
        }
      />

      {showForm ? (
        <DatasetForm
          projectId={projectId}
          onCreated={() => setShowForm(false)}
        />
      ) : null}

      {datasets.isPending ? (
        <LoadingState />
      ) : datasets.isError ? (
        <ErrorState
          title="Could not load datasets"
          message={apiErrorMessage(
            datasets.error,
            "The API did not respond.",
          )}
          onRetry={() => void datasets.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No datasets yet"
          description="Add a dataset of evaluation cases to compare system versions against."
          action={
            !showForm ? (
              <Button onClick={() => setShowForm(true)}>New dataset</Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH className="w-1/2">Name</TH>
              <TH>Version</TH>
              <TH>Cases</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {list.map((dataset) => (
              <TR key={dataset.id} className="hover:bg-surface-raised">
                <TD>
                  <Link
                    href={`/projects/${projectId}/datasets/${dataset.id}`}
                    className="font-medium text-fg transition-colors hover:text-accent"
                  >
                    {dataset.name}
                  </Link>
                </TD>
                <TD className="tabular-nums text-fg-muted">
                  v{dataset.version}
                </TD>
                <TD className="tabular-nums text-fg-muted">
                  {dataset.cases.length}
                </TD>
                <TD className="whitespace-nowrap text-fg-muted">
                  {formatDateTime(dataset.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
