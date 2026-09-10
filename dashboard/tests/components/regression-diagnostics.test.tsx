import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { RegressionDiagnosticsPanel } from "@/app/projects/[projectId]/experiments/[experimentId]/regression-diagnostics";
import type {
  DatasetCase,
  EvaluationRun,
  RegressionDiagnostics,
} from "@/lib/api/types";

function run(overrides: Partial<EvaluationRun>): EvaluationRun {
  return {
    id: "r",
    system_version_id: "v1",
    case_id: "case-1",
    repeat_index: 0,
    output: "out",
    error: null,
    usage: {
      prompt_tokens: 1,
      completion_tokens: 1,
      total_tokens: 2,
      cost_usd: 0,
      latency_ms: 5,
    },
    scores: [],
    retrieval: [],
    tool_calls: [],
    created_at: "2026-09-10T00:00:00Z",
    ...overrides,
  };
}

const CASE: DatasetCase = {
  id: "case-1",
  input: "what is 2+2?",
  expected_output: "4",
  origin: "authored",
  source_trace_id: null,
  expected_retrieval_ids: [],
  expected_tool_calls: [],
};

function diagnostics(
  overrides: Partial<RegressionDiagnostics>,
): RegressionDiagnostics {
  return {
    experiment_id: "e1",
    evaluation_result_id: "res-1",
    baseline_version_id: "v1",
    candidate_version_id: "v2",
    matched_pairs: 2,
    regressing_pairs: 1,
    regressing_cases: 1,
    available: true,
    categories: [
      { category: "evaluator_regression", pairs: 1, cases: 1 },
    ],
    evaluators: [
      {
        evaluator: "contains",
        pairs: 1,
        cases: 1,
        pass_to_fail: 1,
        score_drop: 0,
      },
    ],
    cases: [
      {
        case_id: "case-1",
        categories: ["evaluator_regression"],
        evaluators: ["contains"],
        provider_failure: false,
        finding_count: 1,
        representative: {
          repeat_index: 0,
          baseline_run_id: "base-r0",
          candidate_run_id: "cand-r0",
        },
      },
    ],
    findings: [
      {
        case_id: "case-1",
        repeat_index: 0,
        baseline_run_id: "base-r0",
        candidate_run_id: "cand-r0",
        category: "evaluator_regression",
        kind: "evaluator_pass_to_fail",
        evaluator: "contains",
        baseline_detail: "pass",
        candidate_detail: "fail",
      },
    ],
    ...overrides,
  };
}

const RUNS = [
  run({
    id: "base-r0",
    system_version_id: "v1",
    scores: [
      { evaluator: "contains", family: "deterministic", score: 1, passed: true },
    ],
  }),
  run({
    id: "cand-r0",
    system_version_id: "v2",
    output: "5",
    scores: [
      { evaluator: "contains", family: "deterministic", score: 0, passed: false },
    ],
  }),
];

describe("RegressionDiagnosticsPanel", () => {
  it("renders nothing when diagnostics are unavailable", () => {
    const { container } = render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({ available: false })}
        runs={[]}
        blocked
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("states plainly when a run has no regressing cases", () => {
    render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({
          regressing_pairs: 0,
          regressing_cases: 0,
          categories: [],
          evaluators: [],
          cases: [],
          findings: [],
        })}
        runs={RUNS}
        blocked={false}
      />,
    );
    expect(screen.getByText("Regressing cases")).toBeInTheDocument();
    expect(
      screen.getByText(/No case-level regressions/i),
    ).toBeInTheDocument();
  });

  it("titles the panel 'Why was this blocked?' for a BLOCK and lists category counts", () => {
    render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({})}
        runs={RUNS}
        datasetCases={[CASE]}
        blocked
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Why was this blocked?" }),
    ).toBeInTheDocument();
    // category summary chip carries the count
    expect(screen.getAllByText("Evaluator regression").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 pair · 1 case/)).toBeInTheDocument();
    // per-evaluator breakdown
    expect(screen.getByText(/1 pass→fail/)).toBeInTheDocument();
  });

  it("expands a case to a baseline-vs-candidate inspection with the evaluator transition", async () => {
    const user = userEvent.setup();
    render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({})}
        runs={RUNS}
        datasetCases={[CASE]}
        blocked
      />,
    );

    await user.click(screen.getByText(/case-1/));

    expect(screen.getByText("what is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("Expected output")).toBeInTheDocument();
    expect(screen.getByText("Baseline run")).toBeInTheDocument();
    expect(screen.getByText("Candidate run")).toBeInTheDocument();

    // PASS -> FAIL transition row, tinted as a regression
    const transitionRow = screen.getAllByRole("row").find((r) =>
      within(r).queryByText("contains"),
    )!;
    expect(transitionRow).toHaveTextContent(/pass · 1\.000/);
    expect(transitionRow).toHaveTextContent(/fail · 0\.000/);
    expect(transitionRow.className).toContain("text-block");
  });

  it("handles a text-only case with no retrieval or tool evidence", async () => {
    const user = userEvent.setup();
    render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({})}
        runs={RUNS}
        datasetCases={[CASE]}
        blocked
      />,
    );
    await user.click(screen.getByText(/case-1/));
    // RunEvidence still renders the scores section, no RAG/agent sections
    expect(screen.getAllByText("Evaluator scores").length).toBeGreaterThan(0);
    expect(screen.queryByText("Retrieved context")).not.toBeInTheDocument();
    expect(screen.queryByText("Tool trajectory")).not.toBeInTheDocument();
  });

  it("shows a provider-failure category and marks the case", () => {
    render(
      <RegressionDiagnosticsPanel
        diagnostics={diagnostics({
          categories: [
            { category: "provider_execution_failure", pairs: 1, cases: 1 },
          ],
          evaluators: [],
          cases: [
            {
              case_id: "case-1",
              categories: ["provider_execution_failure"],
              evaluators: [],
              provider_failure: true,
              finding_count: 1,
              representative: {
                repeat_index: 0,
                baseline_run_id: "base-r0",
                candidate_run_id: "cand-r0",
              },
            },
          ],
          findings: [
            {
              case_id: "case-1",
              repeat_index: 0,
              baseline_run_id: "base-r0",
              candidate_run_id: "cand-r0",
              category: "provider_execution_failure",
              kind: "provider_failure",
              evaluator: null,
              baseline_detail: "completed",
              candidate_detail: "503 upstream unavailable",
            },
          ],
        })}
        runs={RUNS}
        datasetCases={[CASE]}
        blocked
      />,
    );
    expect(
      screen.getAllByText("Provider / execution failure").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/1 pair · 1 case/)).toBeInTheDocument();
  });
});
