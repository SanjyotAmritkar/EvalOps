import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/ui/copy-button";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import type { MetricEvidence, MetricLine } from "@/lib/api/types";
import {
  formatMetricValue,
  formatPercent,
  formatSignedPercent,
} from "@/lib/format";
import { metricLabel } from "@/lib/metric-labels";
import {
  EVIDENCE_STATUS_LABEL,
  METRIC_STATUS_LABEL,
  blockingSentence,
  evidenceStatus,
  metricDisplayStatus,
  metricStatus,
  metricStatusTone,
} from "@/lib/release-decision";

const STATUS_TEXT_TONE = {
  block: "text-block",
  warn: "text-warn",
  pass: "text-pass",
  muted: "text-fg-subtle",
} as const;

/**
 * The authoritative release decision for a completed experiment. Fed by a
 * persisted EvaluationResult (whose decision, advisories and evidence the API
 * recomputes on read), so a refresh shows the same thing.
 *
 * The decision, the advisory text and every statistic are the backend's — this
 * only formats them. No bootstrap or gate logic runs here.
 */
export function ReleaseDecision({
  decision,
  gated,
  reasons,
  metrics,
  resultId,
  advisories = [],
  evidence = [],
}: {
  decision: string;
  gated: boolean;
  reasons: string[];
  metrics: MetricLine[];
  resultId: string;
  advisories?: string[];
  evidence?: MetricEvidence[];
}) {
  const blocking = metrics.filter((metric) => metric.regression);
  const improved = metrics.filter(
    (metric) => metricStatus(metric) === "improved",
  );
  const passWithCaveats =
    gated && decision === "pass" && advisories.length > 0;

  const lineByMetric = new Map(metrics.map((m) => [m.metric, m]));
  // Deterministic point-only metrics: gated, but no paired-bootstrap evidence.
  const evidenceMetrics = new Set(evidence.map((e) => e.metric));
  const deterministicGated = metrics.filter(
    (m) => m.threshold !== null && !evidenceMetrics.has(m.metric),
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
          Release decision
        </span>
        <span className="inline-flex flex-wrap items-center gap-2">
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
          {passWithCaveats ? (
            <Badge tone="warn">with unverified concerns</Badge>
          ) : null}
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
      ) : passWithCaveats ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-warn/40 bg-surface px-3 py-2.5">
          <p className="text-sm font-medium text-warn">
            Passed, but {advisories.length} threshold breach
            {advisories.length === 1 ? "" : "es"} could not be confirmed
            statistically. Do not read this as an unconditional pass:
          </p>
          <ul className="list-disc pl-5 text-sm text-fg-muted">
            {advisories.map((advisory, index) => (
              <li key={index}>{advisory}</li>
            ))}
          </ul>
          <p className="text-xs text-fg-subtle">
            Re-run with more repeats or a larger dataset to get a conclusive
            result.
          </p>
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
              const status = metricDisplayStatus(metric);
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
                        STATUS_TEXT_TONE[metricStatusTone(status)],
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

      {evidence.length > 0 ? (
        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
            Statistical evidence · paired bootstrap
          </span>
          <ul className="flex flex-col gap-2">
            {evidence.map((entry) => (
              <EvidenceRow
                key={entry.metric}
                entry={entry}
                line={lineByMetric.get(entry.metric)}
              />
            ))}
          </ul>
          {deterministicGated.length > 0 ? (
            <p className="text-xs text-fg-subtle">
              {deterministicGated.map((m) => metricLabel(m.metric)).join(", ")}{" "}
              {deterministicGated.length === 1 ? "is" : "are"} gated on the point
              comparison only — no paired-bootstrap interval.
            </p>
          ) : null}
        </div>
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
          {advisories.length > 0 ? (
            <ul className="list-disc pl-5">
              {advisories.map((advisory, index) => (
                <li key={index} className="font-mono">
                  {advisory}
                </li>
              ))}
            </ul>
          ) : null}
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

function EvidenceRow({
  entry,
  line,
}: {
  entry: MetricEvidence;
  line: MetricLine | undefined;
}) {
  const status = evidenceStatus(entry, line);
  const tone =
    status === "supports-regression"
      ? "block"
      : status === "inconclusive" || status === "insufficient"
        ? "warn"
        : "neutral";

  const ci =
    entry.ci_low === null || entry.ci_high === null
      ? "not computed"
      : `[${formatMetricValue(entry.metric, entry.ci_low)}, ${formatMetricValue(
          entry.metric,
          entry.ci_high,
        )}]`;

  return (
    <li className="flex flex-col gap-1 rounded-md border border-border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <span className="flex flex-col">
          <span className="text-[13px] font-medium text-fg">
            {metricLabel(entry.metric)}
          </span>
          <span className="font-mono text-[11px] text-fg-subtle">
            {entry.metric}
          </span>
        </span>
        <Badge tone={tone}>{EVIDENCE_STATUS_LABEL[status]}</Badge>
      </div>
      <p className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-fg-muted tabular-nums">
        <span>
          {entry.n_pairs} paired sample{entry.n_pairs === 1 ? "" : "s"}
        </span>
        <span aria-hidden>·</span>
        <span>
          {formatMetricValue(entry.metric, entry.baseline.mean)} →{" "}
          {formatMetricValue(entry.metric, entry.candidate.mean)}
        </span>
        <span aria-hidden>·</span>
        <span>
          {entry.relative_change === null
            ? formatMetricValue(entry.metric, entry.delta)
            : formatSignedPercent(entry.relative_change)}
        </span>
        <span aria-hidden>·</span>
        <span>
          {formatPercent(entry.confidence_level)} CI {ci}
        </span>
        {entry.dropped_provider_failures > 0 ? (
          <>
            <span aria-hidden>·</span>
            <span className="text-fg-subtle">
              {entry.dropped_provider_failures} pair
              {entry.dropped_provider_failures === 1 ? "" : "s"} dropped (provider
              error)
            </span>
          </>
        ) : null}
      </p>
    </li>
  );
}
