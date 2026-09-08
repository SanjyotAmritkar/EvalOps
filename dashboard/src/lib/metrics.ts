/**
 * The closed set of metric names the release gate understands (see the Python
 * `gate` module). Evaluator pass-rates are also valid but their names depend on
 * the evaluators chosen at run time, so they are entered free-form.
 */
export const KNOWN_POLICY_METRICS = [
  "success_rate",
  "latency_ms.mean",
  "latency_ms.p95",
  "cost_usd.total",
] as const;
