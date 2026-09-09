import { CopyButton } from "@/components/ui/copy-button";
import { DecisionBadge } from "@/components/ui/decision-badge";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import type { RunResponse } from "@/lib/api/types";
import {
  formatDelta,
  formatMetricValue,
  formatSignedPercent,
} from "@/lib/format";
import { metricLabel } from "@/lib/metric-labels";

/** Renders the synchronous RunResponse returned by POST /experiments/{id}/run.
 * A gated BLOCK is a completed run, not an error. */
export function RunSummary({ result }: { result: RunResponse }) {
  const { counts } = result;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-3">
          <DecisionBadge decision={result.decision} gated={result.gated} />
          <span className="text-sm font-medium text-fg">
            Run complete
          </span>
        </div>
        <p
          className={
            counts.failures > 0
              ? "text-sm font-medium text-block"
              : "text-sm text-fg-muted"
          }
        >
          {counts.cases} case{counts.cases === 1 ? "" : "s"} · {counts.runs} runs
          · {counts.failures} failure{counts.failures === 1 ? "" : "s"}
        </p>
      </div>

      {!result.gated ? (
        <p className="text-sm text-fg-muted">
          No release policy is attached, so this run is a comparison only — no
          PASS / BLOCK decision was made.
        </p>
      ) : null}

      {counts.failures > 0 ? (
        <p className="text-sm text-fg-muted">
          {counts.failures} run{counts.failures === 1 ? "" : "s"} recorded a
          provider error. Those runs count as failures in the metrics below.
        </p>
      ) : null}

      {result.reasons.length > 0 ? (
        <div className="flex flex-col gap-1 rounded-md border border-block/30 bg-surface px-3 py-2">
          <p className="text-sm font-medium text-block">Why it blocked</p>
          <ul className="list-disc pl-5 text-sm text-fg-muted">
            {result.reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.metrics.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
              <TH className="text-right">Baseline</TH>
              <TH className="text-right">Candidate</TH>
              <TH className="text-right">Δ</TH>
              <TH className="text-right">Δ%</TH>
              <TH className="text-right">Threshold</TH>
              <TH>Status</TH>
            </TR>
          </THead>
          <TBody>
            {result.metrics.map((metric) => (
              <TR key={metric.metric}>
                <TD>
                  <span className="flex flex-col">
                    <span className="text-[13px] font-medium text-fg">
                      {metricLabel(metric.metric)}
                    </span>
                    <span className="font-mono text-[11px] text-fg-subtle">
                      {metric.metric}
                    </span>
                  </span>
                </TD>
                <TD className="text-right tabular-nums text-fg-muted">
                  {formatMetricValue(metric.metric, metric.baseline_value)}
                </TD>
                <TD className="text-right tabular-nums text-fg-muted">
                  {formatMetricValue(metric.metric, metric.candidate_value)}
                </TD>
                <TD className="text-right tabular-nums text-fg-muted">
                  {formatDelta(metric.delta)}
                </TD>
                <TD className="text-right tabular-nums text-fg-muted">
                  {formatSignedPercent(metric.relative_delta)}
                </TD>
                <TD className="text-right tabular-nums text-fg-subtle">
                  {metric.threshold === null
                    ? "—"
                    : `≤ ${Number((metric.threshold * 100).toFixed(2))}%`}
                </TD>
                <TD>
                  {metric.regression ? (
                    <span className="text-xs font-medium text-block">
                      regression
                    </span>
                  ) : (
                    <span className="text-xs text-fg-subtle">ok</span>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
        <span>Evaluation result</span>
        <code className="font-mono text-fg-muted">
          {result.evaluation_result_id}
        </code>
        <CopyButton value={result.evaluation_result_id} />
      </div>

      <p className="text-xs text-fg-subtle">
        Full regression analysis will live on a dedicated results page in a later
        update.
      </p>
    </div>
  );
}
