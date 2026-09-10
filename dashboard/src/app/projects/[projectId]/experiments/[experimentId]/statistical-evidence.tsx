import { Badge } from "@/components/ui/badge";
import { InfoHint } from "@/components/ui/info-hint";
import type { MetricEvidence, MetricLine } from "@/lib/api/types";
import {
  formatMetricValue,
  formatPercent,
  formatSignedPercent,
} from "@/lib/format";
import { metricLabel } from "@/lib/metric-labels";
import {
  EVIDENCE_STATUS_LABEL,
  evidenceStatus,
} from "@/lib/release-decision";

function toneFor(status: ReturnType<typeof evidenceStatus>) {
  if (status === "supports-regression") return "block" as const;
  if (status === "inconclusive" || status === "insufficient")
    return "warn" as const;
  return "neutral" as const;
}

function EvidenceEntry({
  entry,
  line,
}: {
  entry: MetricEvidence;
  line: MetricLine | undefined;
}) {
  const status = evidenceStatus(entry, line);
  const ci =
    entry.ci_low === null || entry.ci_high === null
      ? "not computed"
      : `[${formatMetricValue(entry.metric, entry.ci_low)}, ${formatMetricValue(
          entry.metric,
          entry.ci_high,
        )}]`;

  return (
    <li className="flex flex-col rounded-lg border border-border">
      {/* primary layer — always visible */}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2.5">
        <span className="flex flex-col">
          <span className="text-[14px] font-medium text-fg">
            {metricLabel(entry.metric)}
          </span>
          <span className="font-mono text-[12px] text-fg-subtle">
            {entry.n_pairs} paired sample{entry.n_pairs === 1 ? "" : "s"}
          </span>
        </span>
        <Badge tone={toneFor(status)}>{EVIDENCE_STATUS_LABEL[status]}</Badge>
      </div>

      {/* operational detail — one level down */}
      <details className="border-t border-border px-3 py-2 text-[13px] text-fg-muted">
        <summary className="cursor-pointer text-fg-subtle">
          View statistical evidence
        </summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 tabular-nums">
          <dt className="text-fg-subtle">Baseline → candidate</dt>
          <dd>
            {formatMetricValue(entry.metric, entry.baseline.mean)} →{" "}
            {formatMetricValue(entry.metric, entry.candidate.mean)}
          </dd>
          <dt className="text-fg-subtle">Observed delta</dt>
          <dd>{formatMetricValue(entry.metric, entry.delta)}</dd>
          <dt className="text-fg-subtle">Relative change</dt>
          <dd>
            {entry.relative_change === null
              ? "—"
              : formatSignedPercent(entry.relative_change)}
          </dd>
          <dt className="text-fg-subtle">Paired N</dt>
          <dd>{entry.n_pairs}</dd>
          {entry.dropped_provider_failures > 0 ? (
            <>
              <dt className="text-fg-subtle">Dropped pairs</dt>
              <dd>
                {entry.dropped_provider_failures} (provider error on one side)
              </dd>
            </>
          ) : null}
        </dl>
        <p className="mt-1 tabular-nums">
          {formatPercent(entry.confidence_level)} CI {ci}
        </p>
        <details className="mt-2 text-[12px] text-fg-subtle">
          <summary className="cursor-pointer">Method</summary>
          <p className="mt-1">
            {entry.method}. Baseline σ{" "}
            {formatMetricValue(entry.metric, entry.baseline.stdev)}, candidate σ{" "}
            {formatMetricValue(entry.metric, entry.candidate.stdev)}. The
            interval is deterministic given its seed; the dashboard never
            recomputes it.
          </p>
        </details>
      </details>
    </li>
  );
}

/**
 * Progressive disclosure over the Phase 5 paired-bootstrap evidence. The
 * primary line is a plain-language status + the paired-sample count; the
 * numbers (delta, 95% CI, summaries) sit one disclosure down, the bootstrap
 * method one further. No confidence interval or verdict is computed here —
 * every value is the backend's.
 */
export function StatisticalEvidence({
  evidence,
  metrics,
  deterministicGatedLabels,
}: {
  evidence: MetricEvidence[];
  metrics: MetricLine[];
  deterministicGatedLabels: string[];
}) {
  if (evidence.length === 0) return null;
  const lineByMetric = new Map(metrics.map((m) => [m.metric, m]));

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-fg">Statistical evidence</h2>
        <InfoHint label="How the statistical evidence is computed" />
      </div>
      <p className="text-[13px] leading-relaxed text-fg-subtle">
        Paired bootstrap over baseline vs candidate runs matched by case and
        repeat. The interval, not the raw average, decides whether a breach
        BLOCKs.
      </p>
      <ul className="flex flex-col gap-2">
        {evidence.map((entry) => (
          <EvidenceEntry
            key={entry.metric}
            entry={entry}
            line={lineByMetric.get(entry.metric)}
          />
        ))}
      </ul>
      {deterministicGatedLabels.length > 0 ? (
        <p className="text-[13px] text-fg-subtle">
          {deterministicGatedLabels.join(", ")}{" "}
          {deterministicGatedLabels.length === 1 ? "is" : "are"} gated on the
          point comparison only — no paired-bootstrap interval.
        </p>
      ) : null}
    </section>
  );
}
