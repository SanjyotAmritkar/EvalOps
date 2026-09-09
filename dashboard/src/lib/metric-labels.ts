/**
 * Presentation-only mapping from the backend's metric identifiers to
 * human-readable names. The identifiers themselves are unchanged — these labels
 * exist purely so a first-time reader can understand a release policy.
 */

const KNOWN: Record<string, string> = {
  success_rate: "Reliability",
  "contains.pass_rate": "Answer quality",
  "regex_match.pass_rate": "Pattern compliance",
  "exact_match.pass_rate": "Exact-answer match",
  "latency_ms.mean": "Mean latency",
  "latency_ms.p95": "P95 latency",
  "cost_usd.total": "Cost",
};

/** Friendly name for a metric identifier; falls back to a tidied identifier. */
export function metricLabel(metric: string): string {
  const known = KNOWN[metric];
  if (known) return known;
  if (metric.endsWith(".pass_rate")) {
    return `${metric.slice(0, -".pass_rate".length)} pass rate`;
  }
  return metric;
}

/** Plain-language reading of a fractional regression tolerance. */
export function describeThreshold(value: number): string {
  if (value <= 0) return "No regression allowed";
  const percent = Number((value * 100).toFixed(2));
  return `Up to ${percent}% regression`;
}
