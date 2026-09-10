import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricComparison } from "@/app/projects/[projectId]/experiments/[experimentId]/metric-comparison";
import type { MetricLine } from "@/lib/api/types";

function line(overrides: Partial<MetricLine>): MetricLine {
  return {
    metric: "success_rate",
    baseline_value: 1,
    candidate_value: 1,
    delta: 0,
    relative_delta: 0,
    direction: "higher_is_better",
    threshold: 0.1,
    adverse_change: 0,
    regression: false,
    gate_outcome: "pass",
    ...overrides,
  };
}

describe("MetricComparison", () => {
  it("groups metrics into Quality / Reliability / Performance and preserves every one", () => {
    render(
      <MetricComparison
        metrics={[
          line({ metric: "success_rate", candidate_value: 0.98 }),
          line({ metric: "contains.pass_rate", candidate_value: 0.8 }),
          line({ metric: "tool_selection.mean_score", candidate_value: 0.7 }),
          line({
            metric: "latency_ms.mean",
            direction: "lower_is_better",
            baseline_value: 40,
            candidate_value: 52,
            threshold: null,
          }),
          line({
            metric: "cost_usd.total",
            direction: "lower_is_better",
            baseline_value: 0.01,
            candidate_value: 0.012,
            threshold: null,
          }),
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Quality" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Reliability" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Performance" }),
    ).toBeInTheDocument();

    // human labels lead; raw identifiers are kept as their own selectable text
    expect(screen.getByText("Answer quality")).toBeInTheDocument();
    expect(screen.getByText("contains.pass_rate")).toBeInTheDocument();
    expect(screen.getByText("Tool selection — mean score")).toBeInTheDocument();
    expect(screen.getByText("tool_selection.mean_score")).toBeInTheDocument();
    expect(screen.getByText("Cost")).toBeInTheDocument();
  });

  it("draws a comparison bar for a normalised metric using the real backend values", () => {
    render(
      <MetricComparison
        metrics={[
          line({
            metric: "contains.pass_rate",
            baseline_value: 0.9,
            candidate_value: 0.5,
            relative_delta: -0.444,
            adverse_change: 0.444,
            regression: true,
            gate_outcome: "regression",
          }),
        ]}
      />,
    );

    // exact values are present as text (the bar only supplements them)
    const row = screen.getByText("Answer quality").closest("li")!;
    expect(within(row).getByText("0.900")).toBeInTheDocument();
    expect(within(row).getByText("0.500")).toBeInTheDocument();

    // the bar widths are derived from those same values
    const bars = row.querySelectorAll<HTMLElement>("[style*='width']");
    expect(bars).toHaveLength(2);
    expect(bars[0]!.style.width).toBe("90%");
    expect(bars[1]!.style.width).toBe("50%");
  });

  it("does not force latency or cost into a normalised bar", () => {
    render(
      <MetricComparison
        metrics={[
          line({
            metric: "latency_ms.mean",
            direction: "lower_is_better",
            baseline_value: 40,
            candidate_value: 90,
            relative_delta: 1.25,
            threshold: 0.2,
            adverse_change: 1.25,
          }),
        ]}
      />,
    );

    const row = screen.getByText("Mean latency").closest("li")!;
    expect(within(row).getByText("40.0 ms")).toBeInTheDocument();
    expect(within(row).getByText("90.0 ms")).toBeInTheDocument();
    expect(row.querySelectorAll("[style*='width']")).toHaveLength(0);
  });

  it("shows the pass rate / mean score legend only when such metrics exist", () => {
    const { rerender } = render(
      <MetricComparison
        metrics={[line({ metric: "contains.pass_rate", candidate_value: 1 })]}
      />,
    );
    expect(screen.getByText(/fraction of evaluator checks/i)).toBeInTheDocument();

    rerender(
      <MetricComparison
        metrics={[
          line({
            metric: "latency_ms.p95",
            direction: "lower_is_better",
            threshold: null,
          }),
        ]}
      />,
    );
    expect(
      screen.queryByText(/fraction of evaluator checks/i),
    ).not.toBeInTheDocument();
  });

  it("labels each row with the backend's gate verdict, not a recomputed one", () => {
    render(
      <MetricComparison
        metrics={[
          line({
            metric: "contains.pass_rate",
            candidate_value: 0.5,
            adverse_change: 0.5,
            regression: true,
            gate_outcome: "regression",
          }),
          line({
            metric: "success_rate",
            candidate_value: 0.95,
            adverse_change: 0.05,
            regression: false,
            gate_outcome: "regression_low_evidence",
          }),
        ]}
      />,
    );
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Breach — low evidence")).toBeInTheDocument();
  });
});
