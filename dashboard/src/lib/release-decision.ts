import type { MetricLine } from "@/lib/api/types";
import { formatPercent } from "@/lib/format";
import { metricLabel } from "@/lib/metric-labels";

/**
 * Per-metric status derived purely from the API's verdict fields
 * (`regression`, `adverse_change`, `threshold`). The gate decision itself is
 * made by the backend — this only classifies each row for display.
 */
export type MetricStatus =
  | "improved"
  | "within-threshold"
  | "regression"
  | "blocked"
  | "unchanged"
  | "n/a";

export function metricStatus(metric: MetricLine): MetricStatus {
  if (metric.regression) return "blocked";
  if (metric.adverse_change === null) return "n/a";
  if (metric.adverse_change < 0) return "improved";
  if (metric.adverse_change > 0) {
    return metric.threshold !== null ? "within-threshold" : "regression";
  }
  return "unchanged";
}

export const METRIC_STATUS_LABEL: Record<MetricStatus, string> = {
  improved: "Improved",
  "within-threshold": "Within threshold",
  regression: "Regression",
  blocked: "Blocked",
  unchanged: "No change",
  "n/a": "—",
};

/**
 * Plain-English sentence for a metric that blocked the release, built from the
 * backend-supplied numbers, e.g.
 * "Answer quality regressed 50%; policy allows up to 10%."
 */
export function blockingSentence(metric: MetricLine): string {
  const name = metricLabel(metric.metric);
  const allowed =
    metric.threshold === null
      ? "no regression"
      : `up to ${formatPercent(metric.threshold)}`;
  if (metric.adverse_change === null) {
    return `${name} regressed from a zero baseline (unbounded); policy allows ${allowed}.`;
  }
  return `${name} regressed ${formatPercent(metric.adverse_change)}; policy allows ${allowed}.`;
}
