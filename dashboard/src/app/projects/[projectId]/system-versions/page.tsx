"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useSystemVersions } from "@/lib/query/system-versions";
import { SystemVersionForm } from "./system-version-form";

export default function SystemVersionsPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const versions = useSystemVersions(projectId);
  const [showForm, setShowForm] = useState(false);

  const list = versions.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="System Versions"
        description="Named, immutable configurations of the system under evaluation — the reproducibility anchor for every experiment."
        actions={
          <Button onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "New system version"}
          </Button>
        }
      />

      {showForm ? (
        <SystemVersionForm
          projectId={projectId}
          onCreated={() => setShowForm(false)}
        />
      ) : null}

      {versions.isPending ? (
        <LoadingState />
      ) : versions.isError ? (
        <ErrorState
          title="Could not load system versions"
          message={apiErrorMessage(versions.error, "The API did not respond.")}
          onRetry={() => void versions.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No system versions yet"
          description="Add the provider, model, and prompt template you want to evaluate."
          action={
            !showForm ? (
              <Button onClick={() => setShowForm(true)}>
                New system version
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Version</TH>
              <TH>Provider</TH>
              <TH>Model</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {list.map((version) => (
              <TR key={version.id} className="hover:bg-surface-raised">
                <TD>
                  <Link
                    href={`/projects/${projectId}/system-versions/${version.id}`}
                    className="font-medium text-fg transition-colors hover:text-accent"
                  >
                    {version.name}
                  </Link>
                </TD>
                <TD className="font-mono text-[13px] text-fg-muted">
                  {version.version}
                </TD>
                <TD>
                  <Badge tone="neutral">{version.provider}</Badge>
                </TD>
                <TD className="font-mono text-[13px] text-fg-muted">
                  {version.model}
                </TD>
                <TD className="whitespace-nowrap text-fg-muted">
                  {formatDateTime(version.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
