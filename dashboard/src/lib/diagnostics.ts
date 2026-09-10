/**
 * Presentation-only helpers for the backend's regression diagnostics
 * (GET /experiments/{id}/diagnostics). No count, category, or case is derived
 * here — every value comes from the API. This module only names things and
 * pairs up evaluator scores for a side-by-side view.
 */

import type {
  DiagnosticFinding,
  EvaluationRun,
  EvaluatorScore,
  RegressionCategory,
} from "@/lib/api/types";

interface CategoryMeta {
  label: string;
  description: string;
}

const CATEGORY_META: Record<string, CategoryMeta> = {
  evaluator_regression: {
    label: "Evaluator regression",
    description:
      "An evaluator that passed on the baseline failed on the candidate, or its graded score dropped.",
  },
  provider_execution_failure: {
    label: "Provider / execution failure",
    description:
      "The candidate errored on a case the baseline completed — the provider or the system under test did not respond.",
  },
  retrieval_regression: {
    label: "Retrieval regression",
    description:
      "A retrieval evaluator (recall or context precision) scored lower on the candidate.",
  },
  groundedness_regression: {
    label: "Groundedness regression",
    description:
      "The lexical groundedness evaluator scored the candidate's answer as less supported by its retrieved context.",
  },
  tool_selection_regression: {
    label: "Tool selection regression",
    description:
      "The candidate called a different set of tools than expected, relative to the baseline.",
  },
  tool_argument_regression: {
    label: "Tool argument regression",
    description:
      "The candidate passed different arguments to a tool than the labelled expectation.",
  },
  tool_execution_failure: {
    label: "Tool execution failure",
    description:
      "A tool the candidate invoked reported a failure where the baseline's tools succeeded.",
  },
  trajectory_regression: {
    label: "Trajectory regression",
    description:
      "The candidate's ordered tool sequence diverged further from the expected trajectory.",
  },
};

function titleCase(slug: string): string {
  return slug
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Human label + one-line description for a diagnostic category. */
export function diagnosticCategory(category: RegressionCategory): CategoryMeta {
  return (
    CATEGORY_META[category] ?? {
      label: titleCase(String(category)),
      description: "A candidate-side regression relative to the baseline.",
    }
  );
}

export interface ScoreTransition {
  evaluator: string;
  baseline: EvaluatorScore | null;
  candidate: EvaluatorScore | null;
  /** True when the pair is a PASS→FAIL or a graded-score drop. */
  regressed: boolean;
}

/**
 * Line up the evaluator scores of a baseline run against a candidate run so the
 * inspector can show "PASS → FAIL" / "1.00 → 0.50". A transition is marked
 * `regressed` only when the evidence supports it (passed went true→false, or the
 * numeric score fell) — never inferred beyond that.
 */
export function scoreTransitions(
  baseline: EvaluationRun | undefined,
  candidate: EvaluationRun | undefined,
): ScoreTransition[] {
  const b = new Map((baseline?.scores ?? []).map((s) => [s.evaluator, s]));
  const c = new Map((candidate?.scores ?? []).map((s) => [s.evaluator, s]));
  const names = Array.from(new Set([...b.keys(), ...c.keys()])).sort();

  return names.map((evaluator) => {
    const baselineScore = b.get(evaluator) ?? null;
    const candidateScore = c.get(evaluator) ?? null;
    const passRegressed =
      baselineScore?.passed === true && candidateScore?.passed === false;
    const scoreRegressed =
      baselineScore != null &&
      candidateScore != null &&
      candidateScore.score < baselineScore.score;
    return {
      evaluator,
      baseline: baselineScore,
      candidate: candidateScore,
      regressed: passRegressed || scoreRegressed,
    };
  });
}

/** Findings for one case, in the API's deterministic order. */
export function findingsForCase(
  findings: DiagnosticFinding[],
  caseId: string,
): DiagnosticFinding[] {
  return findings.filter((f) => f.case_id === caseId);
}
