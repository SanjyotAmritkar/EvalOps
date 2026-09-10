"use client";

import { Fragment } from "react";
import { useParams } from "next/navigation";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { BackLink } from "@/components/layout/back-link";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/ui/copy-button";
import {
  DefinitionItem,
  DefinitionList,
} from "@/components/ui/definition-list";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useDataset } from "@/lib/query/datasets";
import { CaseExpectations } from "../case-expectations";

export default function DatasetDetailPage() {
  const params = useParams<{ projectId: string; datasetId: string }>();
  const projectId = String(params.projectId ?? "");
  const datasetId = String(params.datasetId ?? "");
  const dataset = useDataset(datasetId);

  const backHref = `/projects/${projectId}/datasets`;

  if (dataset.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <BackLink href={backHref} label="Datasets" />
        <LoadingState rows={4} />
      </div>
    );
  }

  if (dataset.isError || !dataset.data) {
    const notFound = isNotFound(dataset.error);
    return (
      <div className="flex flex-col gap-4">
        <BackLink href={backHref} label="Datasets" />
        <ErrorState
          title={notFound ? "Dataset not found" : "Could not load dataset"}
          message={
            notFound
              ? "This dataset does not exist."
              : apiErrorMessage(dataset.error, "The API did not respond.")
          }
          onRetry={notFound ? undefined : () => void dataset.refetch()}
        />
      </div>
    );
  }

  const d = dataset.data;

  return (
    <div className="flex flex-col gap-6">
      <BackLink href={backHref} label="Datasets" />
      <PageHeader
        title={d.name}
        description={`Version ${d.version} · ${d.cases.length} case${d.cases.length === 1 ? "" : "s"}`}
      />

      <DefinitionList>
        <DefinitionItem term="Name">{d.name}</DefinitionItem>
        <DefinitionItem term="Version">
          <span className="tabular-nums">{d.version}</span>
        </DefinitionItem>
        <DefinitionItem term="Cases">
          <span className="tabular-nums">{d.cases.length}</span>
        </DefinitionItem>
        <DefinitionItem term="Created">
          {formatDateTime(d.created_at)}
        </DefinitionItem>
        <DefinitionItem term="ID">
          <span className="inline-flex items-center gap-2">
            <code className="font-mono text-xs text-fg-muted">{d.id}</code>
            <CopyButton value={d.id} />
          </span>
        </DefinitionItem>
      </DefinitionList>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-fg">Cases</h2>
        <Table>
          <THead>
            <TR>
              <TH className="w-10 text-right">#</TH>
              <TH className="w-1/2">Input</TH>
              <TH className="w-1/2">Expected output</TH>
              <TH>Origin</TH>
            </TR>
          </THead>
          <TBody>
            {d.cases.map((testCase, index) => {
              const hasExpectations =
                (testCase.expected_retrieval_ids?.length ?? 0) > 0 ||
                (testCase.expected_tool_calls?.length ?? 0) > 0;
              return (
                <Fragment key={testCase.id}>
                  <TR className={hasExpectations ? "border-b-0" : undefined}>
                    <TD className="text-right tabular-nums text-fg-subtle">
                      {index + 1}
                    </TD>
                    <TD>
                      <pre className="whitespace-pre-wrap break-words font-mono text-[13px] text-fg">
                        {testCase.input}
                      </pre>
                    </TD>
                    <TD>
                      {testCase.expected_output === null ||
                      testCase.expected_output === "" ? (
                        <span className="text-fg-subtle">—</span>
                      ) : (
                        <pre className="whitespace-pre-wrap break-words font-mono text-[13px] text-fg">
                          {testCase.expected_output}
                        </pre>
                      )}
                    </TD>
                    <TD>
                      <div className="flex flex-col gap-1">
                        <Badge tone="neutral">
                          {testCase.origin === "promoted_trace"
                            ? "promoted"
                            : "authored"}
                        </Badge>
                        {testCase.source_trace_id ? (
                          <code className="font-mono text-[11px] text-fg-subtle">
                            {testCase.source_trace_id}
                          </code>
                        ) : null}
                      </div>
                    </TD>
                  </TR>
                  {hasExpectations ? (
                    <TR className="border-t-0">
                      <TD />
                      <TD colSpan={3} className="pt-0">
                        <CaseExpectations testCase={testCase} />
                      </TD>
                    </TR>
                  ) : null}
                </Fragment>
              );
            })}
          </TBody>
        </Table>
      </section>
    </div>
  );
}
