import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { StatisticalEvidence } from "@/app/projects/[projectId]/experiments/[experimentId]/statistical-evidence";
import type { MetricEvidence, MetricLine } from "@/lib/api/types";

function line(overrides: Partial<MetricLine>): MetricLine {
  return {
    metric: "contains.pass_rate",
    baseline_value: 1,
    candidate_value: 0.6,
    delta: -0.4,
    relative_delta: -0.4,
    direction: "higher_is_better",
    threshold: 0.1,
    adverse_change: 0.4,
    regression: true,
    gate_outcome: "regression",
    ...overrides,
  };
}

function evidence(overrides: Partial<MetricEvidence>): MetricEvidence {
  return {
    metric: "contains.pass_rate",
    kind: "binary",
    n_pairs: 8,
    baseline: { n: 8, mean: 1, median: 1, stdev: 0 },
    candidate: { n: 8, mean: 0.6, median: 0.6, stdev: 0.1 },
    paired_delta: { n: 8, mean: -0.4, median: -0.4, stdev: 0.1 },
    delta: -0.4,
    relative_change: -0.4,
    confidence_level: 0.95,
    ci_low: -0.5,
    ci_high: -0.3,
    ci_excludes_zero: true,
    insufficient_evidence: false,
    dropped_provider_failures: 0,
    method: "paired_bootstrap_percentile",
    ...overrides,
  };
}

describe("StatisticalEvidence", () => {
  it("leads with a plain-language status and the paired-sample count", () => {
    render(
      <StatisticalEvidence
        evidence={[evidence({})]}
        metrics={[line({})]}
        deterministicGatedLabels={[]}
      />,
    );
    expect(
      screen.getByRole("heading", { name: /statistical evidence/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("CI supports a regression")).toBeInTheDocument();
    expect(screen.getByText(/8 paired samples/)).toBeInTheDocument();
  });

  it("keeps the numbers behind a disclosure and the method one level deeper", async () => {
    const user = userEvent.setup();
    render(
      <StatisticalEvidence
        evidence={[evidence({})]}
        metrics={[line({})]}
        deterministicGatedLabels={[]}
      />,
    );

    const disclosure = screen.getByText("View statistical evidence");
    // the CI + delta live inside the collapsed <details>
    expect(screen.getByText(/95% CI \[-0\.500, -0\.300\]/)).toBeInTheDocument();
    expect(screen.getByText("Method")).toBeInTheDocument();

    await user.click(disclosure);
    expect(screen.getByText(/Observed delta/)).toBeInTheDocument();
    expect(screen.getByText(/Relative change/)).toBeInTheDocument();
  });

  it("shows 'not computed' rather than a fake interval when the CI is unavailable", () => {
    render(
      <StatisticalEvidence
        evidence={[
          evidence({
            n_pairs: 2,
            ci_low: null,
            ci_high: null,
            ci_excludes_zero: false,
            insufficient_evidence: true,
          }),
        ]}
        metrics={[line({ gate_outcome: "regression_low_evidence", regression: false })]}
        deterministicGatedLabels={[]}
      />,
    );
    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
    expect(screen.getByText(/95% CI not computed/)).toBeInTheDocument();
  });

  it("names point-only gated metrics that carry no bootstrap interval", () => {
    render(
      <StatisticalEvidence
        evidence={[evidence({})]}
        metrics={[line({})]}
        deterministicGatedLabels={["P95 latency", "Cost"]}
      />,
    );
    expect(
      screen.getByText(/P95 latency, Cost are gated on the point comparison only/),
    ).toBeInTheDocument();
  });

  it("renders nothing when there is no evidence", () => {
    const { container } = render(
      <StatisticalEvidence
        evidence={[]}
        metrics={[line({})]}
        deterministicGatedLabels={[]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
