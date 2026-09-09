import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CalibrationResult } from "@/app/projects/[projectId]/judge-calibrations/calibration-result";
import type {
  JudgeCalibration,
  JudgeCalibrationCase,
  JudgeCalibrationMetrics,
} from "@/lib/api/types";

function metrics(overrides: Partial<JudgeCalibrationMetrics>): JudgeCalibrationMetrics {
  return {
    total: 2,
    scored: 2,
    failures: 0,
    agreements: 2,
    agreement_rate: 1,
    true_positives: 1,
    true_negatives: 1,
    false_positives: 0,
    false_negatives: 0,
    precision: 1,
    recall: 1,
    f1: 1,
    ...overrides,
  };
}

function jcase(overrides: Partial<JudgeCalibrationCase>): JudgeCalibrationCase {
  return {
    input: "What is 2 + 2?",
    output: "4",
    reference: null,
    human_pass: true,
    judge_pass: true,
    judge_score: 0.95,
    judge_reasoning: "matches the expected answer",
    error: null,
    ...overrides,
  };
}

function calibration(
  overrides: Partial<JudgeCalibration> = {},
): JudgeCalibration {
  return {
    id: "cal-1",
    created_at: "2026-09-09T12:00:00Z",
    judge_provider: "openai",
    judge_model: "gpt-4o-mini",
    judge_name: "correctness",
    judge_temperature: 0,
    rubric_id: "judge-v1",
    metrics: metrics({}),
    cases: [
      jcase({}),
      jcase({
        human_pass: false,
        judge_pass: false,
        judge_score: 0.1,
        judge_reasoning: "clearly incorrect",
      }),
    ],
    ...overrides,
  };
}

/** Read the value shown inside a MetricStat identified by its label. */
function stat(label: string): string {
  const el = screen.getByText(label).parentElement as HTMLElement;
  return el.textContent?.replace(label, "").trim() ?? "";
}

describe("CalibrationResult", () => {
  it("renders a perfect calibration from backend values", () => {
    render(<CalibrationResult calibration={calibration()} />);

    expect(stat("Agreement")).toContain("100.0%");
    expect(stat("Precision")).toBe("100.0%");
    expect(stat("Recall")).toBe("100.0%");
    expect(stat("F1")).toBe("100.0%");
    expect(stat("Scored / Failed / Total")).toBe("2 / 0 / 2");
    expect(stat("True pos / True neg")).toBe("1 / 1");

    expect(screen.getByText("correctness")).toBeInTheDocument();
    expect(screen.getByText("openai/gpt-4o-mini")).toBeInTheDocument();
    // one Pass badge per row per side (human + judge), plus a Fail row
    expect(screen.getAllByText("Pass").length).toBe(2);
    expect(screen.getAllByText("Fail").length).toBe(2);
    expect(
      screen.getByText("matches the expected answer"),
    ).toBeInTheDocument();
  });

  it("renders a mixed calibration with visible human/judge disagreements", () => {
    const mixed = calibration({
      metrics: metrics({
        total: 3,
        scored: 3,
        agreements: 1,
        agreement_rate: 1 / 3,
        true_positives: 1,
        true_negatives: 0,
        false_positives: 1,
        false_negatives: 1,
        precision: 0.5,
        recall: 0.5,
        f1: 0.5,
      }),
      cases: [
        jcase({ human_pass: true, judge_pass: true }),
        jcase({ human_pass: false, judge_pass: true, judge_reasoning: "too lenient" }),
        jcase({ human_pass: true, judge_pass: false, judge_reasoning: "too strict" }),
      ],
    });
    render(<CalibrationResult calibration={mixed} />);

    expect(stat("Agreement")).toContain("33.3%");
    expect(stat("Precision")).toBe("50.0%");
    expect(stat("False pos / False neg")).toBe("1 / 1");
    expect(screen.getByText("too lenient")).toBeInTheDocument();
    expect(screen.getByText("too strict")).toBeInTheDocument();
    // both verdict values are shown for the eye to compare
    expect(screen.getAllByText("Pass").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fail").length).toBeGreaterThan(0);
  });

  it("renders undefined metrics as N/A, never 0", () => {
    const undef = calibration({
      metrics: metrics({
        total: 2,
        scored: 2,
        agreements: 1,
        agreement_rate: 0.5,
        true_positives: 0,
        true_negatives: 1,
        false_positives: 0,
        false_negatives: 1,
        precision: null, // TP + FP == 0
        recall: 0, // defined: 0 / (0 + 1)
        f1: null,
      }),
      cases: [
        jcase({ human_pass: true, judge_pass: false }),
        jcase({ human_pass: false, judge_pass: false }),
      ],
    });
    render(<CalibrationResult calibration={undef} />);

    expect(stat("Precision")).toBe("N/A");
    expect(stat("F1")).toBe("N/A");
    expect(stat("Recall")).toBe("0.0%"); // a real zero stays a number
    expect(stat("Agreement")).toContain("50.0%");
  });

  it("marks a failed judge case distinctly and excludes it from metrics", () => {
    const withFailure = calibration({
      metrics: metrics({
        total: 2,
        scored: 1,
        failures: 1,
        agreements: 1,
        agreement_rate: 1,
        true_positives: 1,
        true_negatives: 0,
        false_positives: 0,
        false_negatives: 0,
        precision: 1,
        recall: 1,
        f1: 1,
      }),
      cases: [
        jcase({}),
        jcase({
          human_pass: true,
          judge_pass: null,
          judge_score: null,
          judge_reasoning: null,
          error: "JudgeError: judge reply is not a JSON object",
        }),
      ],
    });
    render(<CalibrationResult calibration={withFailure} />);

    const failedRow = within(screen.getByTestId("calibration-case-failed"));
    expect(failedRow.getByText("Judge failed")).toBeInTheDocument();
    expect(
      failedRow.getByText("JudgeError: judge reply is not a JSON object"),
    ).toBeInTheDocument();
    expect(failedRow.getByText("N/A")).toBeInTheDocument(); // failed row's score cell
    expect(stat("Scored / Failed / Total")).toBe("1 / 1 / 2");
    // explanatory copy
    expect(
      screen.getByText(/does not affect release gating/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/excluded from every metric/i),
    ).toBeInTheDocument();
  });

  it("scopes the reference-only example correctly", () => {
    const withRef = calibration({
      cases: [jcase({ reference: "4", judge_reasoning: "consistent with reference" })],
      metrics: metrics({ total: 1, scored: 1, true_negatives: 0, agreements: 1 }),
    });
    render(<CalibrationResult calibration={withRef} />);
    expect(
      within(screen.getByText(/Per-example/i).parentElement as HTMLElement)
        .getByText("consistent with reference"),
    ).toBeInTheDocument();
  });
});
