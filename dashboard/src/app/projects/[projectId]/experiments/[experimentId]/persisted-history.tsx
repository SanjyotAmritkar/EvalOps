"use client";

import { Fragment, useState } from "react";
import { ChevronRightIcon } from "@/components/icons";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { apiErrorMessage } from "@/lib/api/errors";
import type { EvaluationRun, SystemVersion } from "@/lib/api/types";
import { formatDateTime, shortId } from "@/lib/format";
import { useExperimentRuns } from "@/lib/query/experiments";
import { RunEvidence } from "./run-evidence";

/**
 * Run history for a completed experiment. The first layer is a one-line
 * summary — when it ran, how many runs, how many failed, and how it relates to
 * the stored decision. The raw per-run records (with their retrieval / tool
 * evidence) stay one disclosure down, so a reader is not asked to scan runs
 * before understanding the result.
 */
export function PersistedHistory({
  experimentId,
  baseline,
  candidate,
  resultCreatedAt,
  decisionLabel,
}: {
  experimentId: string;
  baseline?: SystemVersion;
  candidate?: SystemVersion;
  resultCreatedAt?: string;
  decisionLabel?: string;
}) {
  const runs = useExperimentRuns(experimentId);
  const runList = runs.data ?? [];
  const failures = runList.filter((run) => run.error !== null).length;
  const [openId, setOpenId] = useState<string | null>(null);

  const versionName = (id: string) => {
    if (baseline && id === baseline.id) {
      return `${baseline.name} ${baseline.version}`;
    }
    if (candidate && id === candidate.id) {
      return `${candidate.name} ${candidate.version}`;
    }
    return shortId(id);
  };

  const evidenceKind = (run: EvaluationRun) => {
    const retrieval = run.retrieval ?? [];
    const toolCalls = run.tool_calls ?? [];
    const parts: string[] = [];
    if (retrieval.length > 0) parts.push(`${retrieval.length} retrieved`);
    if (toolCalls.length > 0)
      parts.push(`${toolCalls.length} tool call${toolCalls.length === 1 ? "" : "s"}`);
    return parts.join(" · ");
  };

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-fg">Run history</h2>

      {runs.isPending ? (
        <p className="text-sm text-fg-subtle">Loading runs…</p>
      ) : runs.isError ? (
        <p className="text-sm text-block">
          {apiErrorMessage(runs.error, "Could not load runs.")}
        </p>
      ) : runList.length === 0 ? (
        <p className="text-sm text-fg-subtle">No runs recorded.</p>
      ) : (
        <>
          <p className="text-[14px] leading-relaxed text-fg-muted">
            {resultCreatedAt ? `Ran ${formatDateTime(resultCreatedAt)} · ` : ""}
            {runList.length} run{runList.length === 1 ? "" : "s"} recorded
            {failures > 0 ? (
              <span className="text-block"> · {failures} with errors</span>
            ) : null}
            {decisionLabel
              ? ` · one stored evaluation result (${decisionLabel})`
              : ""}
            .
          </p>

          <details className="rounded-lg border border-border">
            <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-fg-muted">
              Individual run records
            </summary>
            <div className="overflow-x-auto border-t border-border">
              <Table>
                <THead>
                  <TR>
                    <TH className="w-8" />
                    <TH>Version</TH>
                    <TH>Case</TH>
                    <TH className="text-right">Repeat</TH>
                    <TH>Status</TH>
                    <TH>Evidence</TH>
                    <TH className="text-right">Latency</TH>
                    <TH className="text-right">Tokens</TH>
                  </TR>
                </THead>
                <TBody>
                  {runList.map((run) => {
                    const open = openId === run.id;
                    const kind = evidenceKind(run);
                    return (
                      <Fragment key={run.id}>
                        <TR className={open ? "border-b-0" : undefined}>
                          <TD>
                            <button
                              type="button"
                              aria-label={open ? "Collapse run" : "Expand run"}
                              aria-expanded={open}
                              onClick={() => setOpenId(open ? null : run.id)}
                              className="text-fg-subtle transition-colors hover:text-fg"
                            >
                              <ChevronRightIcon
                                width={14}
                                height={14}
                                className={cn(
                                  "transition-transform",
                                  open && "rotate-90",
                                )}
                              />
                            </button>
                          </TD>
                          <TD>{versionName(run.system_version_id)}</TD>
                          <TD className="font-mono text-[12px] text-fg-subtle">
                            {shortId(run.case_id)}
                          </TD>
                          <TD className="text-right tabular-nums text-fg-muted">
                            {run.repeat_index}
                          </TD>
                          <TD>
                            {run.error === null ? (
                              <span className="text-xs text-fg-subtle">ok</span>
                            ) : (
                              <span
                                className="text-xs font-medium text-block"
                                title={run.error}
                              >
                                error
                              </span>
                            )}
                          </TD>
                          <TD className="text-xs text-fg-subtle">
                            {kind === "" ? "—" : kind}
                          </TD>
                          <TD className="text-right tabular-nums text-fg-muted">
                            {run.usage.latency_ms.toFixed(1)} ms
                          </TD>
                          <TD className="text-right tabular-nums text-fg-muted">
                            {run.usage.total_tokens}
                          </TD>
                        </TR>
                        {open ? (
                          <TR className="border-t-0">
                            <TD />
                            <TD colSpan={7} className="pt-0">
                              <RunEvidence run={run} />
                            </TD>
                          </TR>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </TBody>
              </Table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
