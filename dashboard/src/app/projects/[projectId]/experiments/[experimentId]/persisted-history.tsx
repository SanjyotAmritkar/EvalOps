"use client";

import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { apiErrorMessage } from "@/lib/api/errors";
import type { SystemVersion } from "@/lib/api/types";
import { shortId } from "@/lib/format";
import { useExperimentRuns } from "@/lib/query/experiments";

/**
 * The raw per-run execution records. The release decision and metric
 * comparison are shown prominently by <ReleaseDecision>; this is the
 * lower-level detail behind it.
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

  const versionName = (id: string) => {
    if (baseline && id === baseline.id) {
      return `${baseline.name} ${baseline.version}`;
    }
    if (candidate && id === candidate.id) {
      return `${candidate.name} ${candidate.version}`;
    }
    return shortId(id);
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
                <TH>Version</TH>
                <TH>Case</TH>
                <TH className="text-right">Repeat</TH>
                <TH>Status</TH>
                <TH className="text-right">Latency</TH>
                <TH className="text-right">Tokens</TH>
              </TR>
            </THead>
            <TBody>
              {runList.map((run) => (
                <TR key={run.id}>
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
                  <TD className="text-right tabular-nums text-fg-muted">
                    {run.usage.latency_ms.toFixed(1)} ms
                  </TD>
                  <TD className="text-right tabular-nums text-fg-muted">
                    {run.usage.total_tokens}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}
    </div>
  );
}
