import { CopyButton } from "@/components/ui/copy-button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import type { MetricLine } from "@/lib/api/types";
import {
  formatMetricValue,
  formatPercent,
  formatSignedPercent,
} from "@/lib/format";
import { metricLabel } from "@/lib/metric-labels";
import {
  METRIC_STATUS_LABEL,
  blockingSentence,
  metricStatus,
} from "@/lib/release-decision";

/**
 * The authoritative release decision for a completed experiment. Fed either by
 * the synchronous RunResponse or by a persisted EvaluationResult (whose
 * decision the API recomputes on read) — the two are identical, so a refresh
 * shows the same thing.
 *
 * The decision itself is always the backend's; this only formats it.
 */
export function ReleaseDecision({
  decision,
  gated,
  reasons,
  metrics,
  resultId,
}: {
  decision: string;
  gated: boolean;
  reasons: string[];
  metrics: MetricLine[];
  resultId: string;
}) {
  const blocking = metrics.filter((metric) => metric.regression);
  const improved = metrics.filter(
    (metric) => metricStatus(metric) === "improved",
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          Release decision
        </span>
        <span
          className={cn(
            "inline-flex w-fit items-center rounded-md border px-3 py-1 text-base font-semibold",
            !gated
              ? "border-border text-fg-muted"
              : decision === "pass"
                ? "border-pass/40 text-pass"
                : decision === "block"
                  ? "border-block/40 text-block"
                  : "border-warn/40 text-warn",
          )}
        >
          {!gated
            ? "Not gated"
            : decision === "pass"
              ? "PASS"
              : decision === "block"
                ? "BLOCK"
                : decision.toUpperCase()}
        </span>
      </div>

      {!gated ? (
        <p className="text-sm text-fg-muted">
          No release policy is attached, so this run is a comparison only — no
          PASS or BLOCK was decided.
        </p>
      ) : decision === "block" ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-block/30 bg-surface px-3 py-2.5">
          <p className="text-sm font-medium text-block">
            Blocked — {blocking.length} metric
            {blocking.length === 1 ? "" : "s"} regressed beyond policy:
          </p>
          <ul className="list-disc pl-5 text-sm text-fg-muted">
            {blocking.map((metric) => (
              <li key={metric.metric}>{blockingSentence(metric)}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-fg-muted">
          All gated metrics stayed within the release policy
          {improved.length > 0
            ? `; ${improved.length} metric${improved.length === 1 ? "" : "s"} improved.`
            : "."}
        </p>
      )}

      {metrics.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
              <TH className="text-right">Baseline</TH>
              <TH className="text-right">Candidate</TH>
              <TH className="text-right">Change</TH>
              <TH className="text-right">Allowed</TH>
              <TH>Status</TH>
            </TR>
          </THead>
          <TBody>
            {metrics.map((metric) => {
              const status = metricStatus(metric);
              return (
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
                    {formatSignedPercent(metric.relative_delta)}
                  </TD>
                  <TD className="text-right tabular-nums text-fg-subtle">
                    {metric.threshold === null
                      ? "—"
                      : `≤ ${formatPercent(metric.threshold)}`}
                  </TD>
                  <TD>
                    <span
                      className={cn(
                        "text-xs font-medium",
                        status === "blocked"
                          ? "text-block"
                          : status === "improved"
                            ? "text-pass"
                            : status === "regression"
                              ? "text-warn"
                              : "text-fg-subtle",
                      )}
                    >
                      {METRIC_STATUS_LABEL[status]}
                    </span>
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      ) : null}

      <details className="text-xs text-fg-subtle">
        <summary className="cursor-pointer">Gate output &amp; identifiers</summary>
        <div className="mt-2 flex flex-col gap-2">
          {reasons.length > 0 ? (
            <ul className="list-disc pl-5">
              {reasons.map((reason, index) => (
                <li key={index} className="font-mono">
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <p>No blocking reasons.</p>
          )}
          <span className="inline-flex flex-wrap items-center gap-2">
            <span>Evaluation result</span>
            <code className="font-mono text-fg-muted">{resultId}</code>
            <CopyButton value={resultId} />
          </span>
        </div>
      </details>
    </div>
  );
}
