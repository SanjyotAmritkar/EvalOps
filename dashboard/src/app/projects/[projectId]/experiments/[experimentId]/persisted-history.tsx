"use client";

import { Fragment, useState } from "react";
import { ChevronRightIcon } from "@/components/icons";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { apiErrorMessage } from "@/lib/api/errors";
import type { EvaluationRun, SystemVersion } from "@/lib/api/types";
import { shortId } from "@/lib/format";
import { useExperimentRuns } from "@/lib/query/experiments";
import { RunEvidence } from "./run-evidence";

/**
 * The raw per-run execution records. The release decision and metric
 * comparison are shown prominently by <ReleaseDecision>; this is the
 * lower-level detail behind it. Each row expands to show its evaluator scores
 * and, when the system reported them, its retrieved context / tool trajectory.
 */
export function PersistedHistory({
  experimentId,
  baseline,
  candidate,
}: {
  experimentId: string;
  baseline?: SystemVersion;
  candidate?: SystemVersion;
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
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-medium text-fg-muted">Run records</h3>

      {runs.isPending ? (
        <p className="text-sm text-fg-subtle">Loading runs…</p>
      ) : runs.isError ? (
        <p className="text-sm text-block">
          {apiErrorMessage(runs.error, "Could not load runs.")}
        </p>
      ) : runList.length === 0 ? (
        <p className="text-sm text-fg-subtle">No runs recorded.</p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-fg-muted">
            {runList.length} run{runList.length === 1 ? "" : "s"} recorded
            {failures > 0 ? (
              <span className="text-block"> · {failures} with errors</span>
            ) : null}
          </p>
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
      )}
    </div>
  );
}
