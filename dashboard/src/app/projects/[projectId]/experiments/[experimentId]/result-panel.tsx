import { CopyButton } from "@/components/ui/copy-button";
import type {
  DatasetCase,
  EvaluationResult,
  EvaluationRun,
  RegressionDiagnostics,
} from "@/lib/api/types";
import { metricLabel } from "@/lib/metric-labels";
import { DecisionHero } from "./decision-hero";
import { MetricComparison } from "./metric-comparison";
import { RegressionDiagnosticsPanel } from "./regression-diagnostics";
import { StatisticalEvidence } from "./statistical-evidence";

/**
 * The full result surface for a completed experiment: the decision hero, the
 * grouped metric comparison, the progressively-disclosed statistical evidence,
 * and the deterministic case-level diagnostics. Shared by the persisted view
 * and the just-finished background-job view so both read identically.
 *
 * Everything shown is backend state — the decision, metrics, evidence and
 * diagnostics all arrive computed. No gate or statistic runs in the browser.
 */
export function ResultPanel({
  result,
  diagnostics,
  runs,
  datasetCases,
  policyHref,
}: {
  result: EvaluationResult;
  diagnostics?: RegressionDiagnostics;
  runs: EvaluationRun[];
  datasetCases?: DatasetCase[];
  policyHref?: string;
}) {
  const metrics = result.metrics;
  const evidence = result.evidence ?? [];
  const advisories = result.advisories ?? [];

  const evidenceMetrics = new Set(evidence.map((e) => e.metric));
  const deterministicGatedLabels = metrics
    .filter((m) => m.threshold !== null && !evidenceMetrics.has(m.metric))
    .map((m) => metricLabel(m.metric));

  return (
    <div className="flex flex-col gap-8">
      <DecisionHero
        decision={result.decision}
        gated={result.gated}
        reasons={result.reasons}
        advisories={advisories}
        metrics={metrics}
        policyHref={policyHref}
      />

      <MetricComparison metrics={metrics} />

      <StatisticalEvidence
        evidence={evidence}
        metrics={metrics}
        deterministicGatedLabels={deterministicGatedLabels}
      />

      <RegressionDiagnosticsPanel
        diagnostics={diagnostics}
        runs={runs}
        datasetCases={datasetCases}
        blocked={result.gated && result.decision === "block"}
      />

      <details className="text-[13px] text-fg-subtle">
        <summary className="cursor-pointer">Gate output &amp; identifiers</summary>
        <div className="mt-2 flex flex-col gap-2">
          {result.reasons.length > 0 ? (
            <ul className="list-disc pl-5 font-mono">
              {result.reasons.map((reason, index) => (
                <li key={index}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p>No blocking reasons.</p>
          )}
          {advisories.length > 0 ? (
            <ul className="list-disc pl-5 font-mono">
              {advisories.map((advisory, index) => (
                <li key={index}>{advisory}</li>
              ))}
            </ul>
          ) : null}
          <span className="inline-flex flex-wrap items-center gap-2">
            <span>Evaluation result</span>
            <code className="font-mono text-fg-muted">{result.id}</code>
            <CopyButton value={result.id} />
          </span>
        </div>
      </details>
    </div>
  );
}
