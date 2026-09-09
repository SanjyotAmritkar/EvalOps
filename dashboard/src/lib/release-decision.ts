import type { MetricEvidence, MetricLine } from "@/lib/api/types";
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
  | "breach-inconclusive"
  | "breach-low-evidence"
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

/**
 * Display status that honours the backend's CP 5.2 `gate_outcome`: a threshold
 * breach the backend did not BLOCK (weak or inconclusive evidence) must not
 * read as "Within threshold". Falls back to {@link metricStatus} when the field
 * is absent (older API / stale cache) or the outcome is a plain pass.
 */
export function metricDisplayStatus(metric: MetricLine): MetricStatus {
  switch (metric.gate_outcome) {
    case "regression":
      return "blocked";
    case "regression_inconclusive":
      return "breach-inconclusive";
    case "regression_low_evidence":
      return "breach-low-evidence";
    default:
      return metricStatus(metric);
  }
}

export const METRIC_STATUS_LABEL: Record<MetricStatus, string> = {
  improved: "Improved",
  "within-threshold": "Within threshold",
  regression: "Regression",
  blocked: "Blocked",
  "breach-inconclusive": "Breach — inconclusive",
  "breach-low-evidence": "Breach — low evidence",
  unchanged: "No change",
  "n/a": "—",
};

/** Tone bucket for a status, so the UI need not spell out the mapping twice. */
export function metricStatusTone(
  status: MetricStatus,
): "block" | "warn" | "pass" | "muted" {
  if (status === "blocked") return "block";
  if (
    status === "regression" ||
    status === "breach-inconclusive" ||
    status === "breach-low-evidence"
  ) {
    return "warn";
  }
  if (status === "improved") return "pass";
  return "muted";
}

/**
 * How the paired-bootstrap evidence for one metric reads against the gate.
 * Derived only from backend fields (`insufficient_evidence`, `ci_low`, and the
 * matching metric line's `gate_outcome`) — no statistics are computed here.
 */
export type EvidenceStatus =
  | "supports-regression"
  | "inconclusive"
  | "insufficient"
  | "within-tolerance"
  | "reference-only";

export function evidenceStatus(
  evidence: MetricEvidence,
  line: MetricLine | undefined,
): EvidenceStatus {
  if (evidence.insufficient_evidence || evidence.ci_low === null) {
    return "insufficient";
  }
  switch (line?.gate_outcome) {
    case "regression":
      return "supports-regression";
    case "regression_inconclusive":
      return "inconclusive";
    case "regression_low_evidence":
      return "insufficient";
    case "pass":
      return "within-tolerance";
    default:
      // No gated metric line for this evidence (e.g. cost_usd.mean), or an
      // older API without gate_outcome.
      return line ? "within-tolerance" : "reference-only";
  }
}

export const EVIDENCE_STATUS_LABEL: Record<EvidenceStatus, string> = {
  "supports-regression": "CI supports a regression",
  inconclusive: "Inconclusive",
  insufficient: "Insufficient evidence",
  "within-tolerance": "Within tolerance",
  "reference-only": "Reference only",
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
