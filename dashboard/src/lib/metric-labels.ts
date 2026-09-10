/**
 * Presentation-only mapping from the backend's metric identifiers to
 * human-readable names. The identifiers themselves are unchanged — these labels
 * exist purely so a first-time reader can understand a release policy. No
 * metric value, statistic, or gate outcome is computed here.
 */

const KNOWN: Record<string, string> = {
  success_rate: "Reliability",
  "contains.pass_rate": "Answer quality",
  "regex_match.pass_rate": "Pattern compliance",
  "exact_match.pass_rate": "Exact-answer match",
  "latency_ms.mean": "Mean latency",
  "latency_ms.p95": "P95 latency",
  "cost_usd.total": "Cost",

  // RAG evaluator metrics (CP 9.1)
  "retrieval_recall.pass_rate": "Retrieval recall — pass rate",
  "retrieval_recall.mean_score": "Retrieval recall — mean score",
  "context_precision.pass_rate": "Context precision — pass rate",
  "context_precision.mean_score": "Context precision — mean score",
  "groundedness_lexical.pass_rate": "Answer groundedness (lexical) — pass rate",
  "groundedness_lexical.mean_score": "Answer groundedness (lexical) — mean score",

  // Agent evaluator metrics (CP 9.2)
  "tool_selection.pass_rate": "Tool selection — pass rate",
  "tool_selection.mean_score": "Tool selection — mean score",
  "tool_arguments.pass_rate": "Tool arguments — pass rate",
  "tool_arguments.mean_score": "Tool arguments — mean score",
  "tool_success.pass_rate": "Tool success — pass rate",
  "tool_success.mean_score": "Tool success — mean score",
  "tool_trajectory.pass_rate": "Tool trajectory — pass rate",
  "tool_trajectory.mean_score": "Tool trajectory — mean score",
};

/** "pass rate" | "mean score" | null — the aggregation flavour of the metric. */
export function metricKind(metric: string): "pass_rate" | "mean_score" | null {
  if (metric.endsWith(".pass_rate")) return "pass_rate";
  if (metric.endsWith(".mean_score")) return "mean_score";
  return null;
}

export function metricKindLabel(metric: string): string | null {
  const kind = metricKind(metric);
  return kind === "pass_rate"
    ? "pass rate"
    : kind === "mean_score"
      ? "mean score"
      : null;
}

/** Friendly name for a metric identifier; falls back to a tidied identifier. */
export function metricLabel(metric: string): string {
  const known = KNOWN[metric];
  if (known) return known;
  if (metric.endsWith(".pass_rate")) {
    return `${metric.slice(0, -".pass_rate".length)} pass rate`;
  }
  if (metric.endsWith(".mean_score")) {
    return `${metric.slice(0, -".mean_score".length)} mean score`;
  }
  return metric;
}

/** Plain-language reading of a fractional regression tolerance. */
export function describeThreshold(value: number): string {
  if (value <= 0) return "No regression allowed";
  const percent = Number((value * 100).toFixed(2));
  return `Up to ${percent}% regression`;
}
