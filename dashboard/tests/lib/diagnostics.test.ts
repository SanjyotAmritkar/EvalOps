import { describe, expect, it } from "vitest";
import type { EvaluationRun } from "@/lib/api/types";
import { diagnosticCategory, scoreTransitions } from "@/lib/diagnostics";

function run(scores: EvaluationRun["scores"]): EvaluationRun {
  return {
    id: "r",
    system_version_id: "v",
    case_id: "c",
    repeat_index: 0,
    output: "",
    error: null,
    usage: {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      cost_usd: 0,
      latency_ms: 0,
    },
    scores,
    retrieval: [],
    tool_calls: [],
    created_at: "2026-09-10T00:00:00Z",
  };
}

describe("diagnosticCategory", () => {
  it("names known categories", () => {
    expect(diagnosticCategory("retrieval_regression").label).toBe(
      "Retrieval regression",
    );
    expect(diagnosticCategory("provider_execution_failure").label).toBe(
      "Provider / execution failure",
    );
  });

  it("falls back to a title-cased label for an unknown category", () => {
    expect(diagnosticCategory("some_future_category").label).toBe(
      "Some Future Category",
    );
  });
});

describe("scoreTransitions", () => {
  it("marks a PASS→FAIL transition as regressed", () => {
    const [t] = scoreTransitions(
      run([{ evaluator: "contains", family: "deterministic", score: 1, passed: true }]),
      run([{ evaluator: "contains", family: "deterministic", score: 0, passed: false }]),
    );
    expect(t!.regressed).toBe(true);
  });

  it("marks a graded score drop as regressed", () => {
    const [t] = scoreTransitions(
      run([{ evaluator: "judge", family: "llm_judge", score: 0.9, passed: true }]),
      run([{ evaluator: "judge", family: "llm_judge", score: 0.6, passed: true }]),
    );
    expect(t!.regressed).toBe(true);
  });

  it("does not mark an improvement or a steady score", () => {
    const [t] = scoreTransitions(
      run([{ evaluator: "contains", family: "deterministic", score: 0.5, passed: false }]),
      run([{ evaluator: "contains", family: "deterministic", score: 1, passed: true }]),
    );
    expect(t!.regressed).toBe(false);
  });

  it("keeps an evaluator that only ran on one side", () => {
    const rows = scoreTransitions(
      run([{ evaluator: "a", family: "deterministic", score: 1, passed: true }]),
      run([{ evaluator: "b", family: "deterministic", score: 1, passed: true }]),
    );
    expect(rows.map((r) => r.evaluator)).toEqual(["a", "b"]);
    expect(rows.every((r) => r.regressed === false)).toBe(true);
  });
});
