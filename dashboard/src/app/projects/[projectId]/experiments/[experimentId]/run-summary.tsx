import type { RunResponse } from "@/lib/api/types";
import { ReleaseDecision } from "./release-decision";

/** The just-completed run (synchronous RunResponse). A gated BLOCK is a
 * completed run, not an error. */
export function RunSummary({ result }: { result: RunResponse }) {
  const { counts } = result;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-fg">Run complete</p>
        <p
          className={
            counts.failures > 0
              ? "text-sm font-medium text-block"
              : "text-sm text-fg-muted"
          }
        >
          {counts.cases} case{counts.cases === 1 ? "" : "s"} · {counts.runs} runs
          · {counts.failures} failure{counts.failures === 1 ? "" : "s"}
        </p>
        {counts.failures > 0 ? (
          <p className="text-sm text-fg-muted">
            {counts.failures} run{counts.failures === 1 ? "" : "s"} recorded a
            provider error and count as failures in the metrics below.
          </p>
        ) : null}
      </div>

      <ReleaseDecision
        decision={result.decision}
        gated={result.gated}
        reasons={result.reasons}
        metrics={result.metrics}
        resultId={result.evaluation_result_id}
      />
    </div>
  );
}
