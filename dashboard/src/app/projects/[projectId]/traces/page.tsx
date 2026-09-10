"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { WorkflowSteps } from "@/components/ui/workflow-steps";
import { apiErrorMessage } from "@/lib/api/errors";
import type { ProductionTrace } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useSystemVersions } from "@/lib/query/system-versions";
import { useTrace, useTraces } from "@/lib/query/traces";
import { AddTraceForm } from "./add-trace-form";
import { PromotePanel } from "./promote-panel";
import { TraceDetail } from "./trace-detail";

function truncate(text: string, max = 80): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  return collapsed.length > max ? `${collapsed.slice(0, max)}…` : collapsed;
}

function hasReference(trace: ProductionTrace): boolean {
  return (
    trace.reference_output !== null && trace.reference_output.trim() !== ""
  );
}

export default function ProductionTracesPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");

  const traces = useTraces(projectId);
  const versions = useSystemVersions(projectId);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [openTraceId, setOpenTraceId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);

  const openTrace = useTrace(openTraceId);

  const list = useMemo(() => traces.data ?? [], [traces.data]);

  const versionLabel = (id: string) => {
    const match = versions.data?.find((v) => v.id === id);
    return match ? `${match.name} ${match.version}` : id;
  };
  const versionHref = (id: string) =>
    versions.data?.some((v) => v.id === id)
      ? `/projects/${projectId}/system-versions/${id}`
      : null;

  const selectedTraces = useMemo(
    () => list.filter((t) => selectedIds.has(t.id)),
    [list, selectedIds],
  );

  function toggle(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allSelected = list.length > 0 && selectedIds.size === list.length;
  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(list.map((t) => t.id)));
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Production Traces"
        description="Real interactions captured from the running system. Select representative ones and promote them into a replay dataset that flows through the normal experiment and release-gate workflow."
        actions={
          <Button
            variant="secondary"
            onClick={() => setShowAddForm((value) => !value)}
          >
            {showAddForm ? "Close" : "Add trace"}
          </Button>
        }
      />

      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5">
        <span className="text-[13px] font-medium text-fg-subtle">
          How replay works
        </span>
        <WorkflowSteps
          steps={[
            { label: "Production traffic" },
            { label: "Captured traces" },
            { label: "Select interactions" },
            { label: "Replay dataset" },
            { label: "Baseline vs candidate", tone: "candidate" },
            { label: "Release decision" },
          ]}
        />
        <p className="text-sm text-fg-muted">
          A captured trace&rsquo;s <span className="font-medium text-fg">production output</span>{" "}
          is historical system output, <span className="font-medium text-fg">not</span>{" "}
          evaluation ground truth. Promotion copies each trace&rsquo;s input and its
          optional recorded reference into an ordinary dataset; it never turns the
          production output into an expected answer, and it never modifies the
          traces.
        </p>
      </div>

      {showAddForm ? (
        <AddTraceForm
          projectId={projectId}
          onCreated={() => setShowAddForm(false)}
        />
      ) : null}

      {selectedTraces.length > 0 ? (
        <PromotePanel
          projectId={projectId}
          selectedTraces={selectedTraces}
          onClear={() => setSelectedIds(new Set())}
        />
      ) : null}

      {openTraceId ? (
        openTrace.isPending ? (
          <LoadingState rows={4} />
        ) : openTrace.isError || !openTrace.data ? (
          <ErrorState
            title="Could not load that trace"
            message={apiErrorMessage(openTrace.error, "The API did not respond.")}
            onRetry={() => void openTrace.refetch()}
          />
        ) : (
          <TraceDetail
            trace={openTrace.data}
            systemVersionLabel={versionLabel(openTrace.data.system_version_id)}
            systemVersionHref={versionHref(openTrace.data.system_version_id)}
            onClose={() => setOpenTraceId(null)}
          />
        )
      ) : null}

      {traces.isPending ? (
        <LoadingState />
      ) : traces.isError ? (
        <ErrorState
          title="Could not load traces"
          message={apiErrorMessage(traces.error, "The API did not respond.")}
          onRetry={() => void traces.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No production traces yet"
          description="Traces are captured from your running system. Add one with “Add trace” to try the promote-to-replay-dataset workflow."
          action={
            !showAddForm ? (
              <Button variant="secondary" onClick={() => setShowAddForm(true)}>
                Add trace
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH className="w-10">
                <input
                  type="checkbox"
                  aria-label="Select all traces"
                  checked={allSelected}
                  onChange={toggleAll}
                />
              </TH>
              <TH className="whitespace-nowrap">Captured</TH>
              <TH>System version</TH>
              <TH className="w-1/3">Input</TH>
              <TH>Output</TH>
              <TH>Reference</TH>
              <TH className="text-right">Latency</TH>
              <TH className="text-right">Cost</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {list.map((trace) => {
              const selected = selectedIds.has(trace.id);
              return (
                <TR
                  key={trace.id}
                  className={selected ? "bg-accent/5" : "hover:bg-surface-raised"}
                >
                  <TD>
                    <input
                      type="checkbox"
                      aria-label={`Select trace ${trace.id}`}
                      checked={selected}
                      onChange={() => toggle(trace.id)}
                    />
                  </TD>
                  <TD className="whitespace-nowrap text-fg-muted">
                    {formatDateTime(trace.created_at)}
                  </TD>
                  <TD className="text-fg-muted">
                    {versionLabel(trace.system_version_id)}
                  </TD>
                  <TD>
                    <span className="font-mono text-[13px] text-fg">
                      {truncate(trace.input)}
                    </span>
                  </TD>
                  <TD>
                    {trace.error !== null ? (
                      <Badge tone="block">error</Badge>
                    ) : trace.output === "" ? (
                      <Badge tone="neutral">empty</Badge>
                    ) : (
                      <Badge tone="pass">output</Badge>
                    )}
                  </TD>
                  <TD>
                    {hasReference(trace) ? (
                      <Badge tone="neutral">yes</Badge>
                    ) : (
                      <span className="text-fg-subtle">—</span>
                    )}
                  </TD>
                  <TD className="text-right tabular-nums text-fg-muted">
                    {trace.latency_ms === null
                      ? "—"
                      : `${Math.round(trace.latency_ms)} ms`}
                  </TD>
                  <TD className="text-right tabular-nums text-fg-muted">
                    {trace.cost_usd === null
                      ? "—"
                      : `$${trace.cost_usd.toFixed(4)}`}
                  </TD>
                  <TD className="text-right">
                    <button
                      type="button"
                      onClick={() => setOpenTraceId(trace.id)}
                      className="text-sm text-accent transition-colors hover:underline"
                    >
                      Inspect
                    </button>
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}
    </div>
  );
}
