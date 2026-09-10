import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/cn";
import type { MetricLine } from "@/lib/api/types";
import {
  formatMetricValue,
  formatPercent,
  formatSignedPercent,
} from "@/lib/format";
import {
  METRIC_GROUP_LABEL,
  METRIC_GROUP_ORDER,
  isNormalizedMetric,
  metricGroup,
  metricKind,
  metricLabel,
} from "@/lib/metric-labels";
import {
  METRIC_STATUS_LABEL,
  metricDisplayStatus,
  metricStatusTone,
} from "@/lib/release-decision";

const STATUS_TEXT_TONE = {
  block: "text-block",
  warn: "text-warn",
  pass: "text-pass",
  muted: "text-fg-subtle",
} as const;

/** A baseline vs candidate bar for a [0,1]-normalised metric. Decorative — the
 * exact values sit next to it as text — so it is aria-hidden. */
function ComparisonBars({ line }: { line: MetricLine }) {
  const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  return (
    <div aria-hidden className="mt-2 flex flex-col gap-1">
      {(
        [
          ["Baseline", line.baseline_value, "bg-fg-subtle"],
          [
            "Candidate",
            line.candidate_value,
            line.regression ? "bg-block" : "bg-accent",
          ],
        ] as const
      ).map(([label, value, color]) => (
        <div key={label} className="flex items-center gap-2">
          <span className="w-16 shrink-0 text-[12px] text-fg-subtle">
            {label}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-border/60">
            <div
              className={cn("h-full rounded-full", color)}
              style={{ width: pct(value) }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function MetricRow({ line }: { line: MetricLine }) {
  const status = metricDisplayStatus(line);
  const kind = metricKind(line.metric);
  return (
    <li className="flex flex-col gap-1.5 border-b border-border py-3 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="flex flex-col">
          <span className="text-[15px] font-medium text-fg">
            {metricLabel(line.metric)}
          </span>
          <span className="text-[12px] text-fg-subtle">
            <span className="font-mono">{line.metric}</span>
            {kind ? (
              <span> · {kind === "pass_rate" ? "pass rate" : "mean score"}</span>
            ) : null}
          </span>
        </div>
        <span
          className={cn(
            "text-[13px] font-medium",
            STATUS_TEXT_TONE[metricStatusTone(status)],
          )}
        >
          {METRIC_STATUS_LABEL[status]}
        </span>
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] tabular-nums">
        <div className="flex gap-1.5">
          <dt className="text-fg-subtle">Baseline</dt>
          <dd className="text-fg-muted">
            {formatMetricValue(line.metric, line.baseline_value)}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-fg-subtle">Candidate</dt>
          <dd className="font-medium text-fg">
            {formatMetricValue(line.metric, line.candidate_value)}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-fg-subtle">Change</dt>
          <dd className="text-fg-muted">
            {formatSignedPercent(line.relative_delta)}
          </dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-fg-subtle">Allowed</dt>
          <dd className="text-fg-subtle">
            {line.threshold === null
              ? "not gated"
              : `≤ ${formatPercent(line.threshold)}`}
          </dd>
        </div>
      </dl>

      {isNormalizedMetric(line.metric) ? <ComparisonBars line={line} /> : null}
    </li>
  );
}

/**
 * Every metric the backend produced, grouped Quality / Reliability /
 * Performance / Other, with a baseline→candidate comparison for each. The raw
 * metric id is kept as secondary text; the human label leads. No value,
 * direction, or status is computed here — {@link metricDisplayStatus} only
 * classifies the backend's verdict fields for display.
 */
export function MetricComparison({ metrics }: { metrics: MetricLine[] }) {
  if (metrics.length === 0) return null;

  const groups = METRIC_GROUP_ORDER.map((group) => ({
    group,
    lines: metrics.filter((m) => metricGroup(m.metric) === group),
  })).filter((g) => g.lines.length > 0);

  const hasPassRate = metrics.some((m) => metricKind(m.metric) === "pass_rate");
  const hasMeanScore = metrics.some((m) => metricKind(m.metric) === "mean_score");

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-fg">
          What changed, metric by metric
        </h2>
        {hasPassRate || hasMeanScore ? (
          <InfoHint label="Pass rate vs mean score" />
        ) : null}
      </div>

      {groups.map(({ group, lines }) => (
        <div key={group} className="flex flex-col gap-1">
          <h3 className="text-[13px] font-semibold text-fg-muted">
            {METRIC_GROUP_LABEL[group]}
          </h3>
          <ul className="flex flex-col rounded-lg border border-border px-4">
            {lines.map((line) => (
              <MetricRow key={line.metric} line={line} />
            ))}
          </ul>
        </div>
      ))}

      {hasPassRate || hasMeanScore ? (
        <p className="text-[13px] leading-relaxed text-fg-subtle">
          {hasPassRate ? (
            <>
              <span className="font-medium text-fg-muted">Pass rate</span> is the
              fraction of evaluator checks that met their threshold.
            </>
          ) : null}
          {hasPassRate && hasMeanScore ? " " : null}
          {hasMeanScore ? (
            <>
              <span className="font-medium text-fg-muted">Mean score</span> is the
              average graded evaluator score (0–1) — a regression can show here
              even when the pass rate is unchanged.
            </>
          ) : null}
        </p>
      ) : null}
    </section>
  );
}
