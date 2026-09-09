import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReleaseDecision } from "@/app/projects/[projectId]/experiments/[experimentId]/release-decision";
import type { MetricEvidence, MetricLine } from "@/lib/api/types";

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

function evidence(overrides: Partial<MetricEvidence>): MetricEvidence {
  return {
    metric: "success_rate",
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

describe("ReleaseDecision — statistical states", () => {
  it("renders a statistically confirmed BLOCK with its blocking sentence and CI", () => {
    render(
      <ReleaseDecision
        decision="block"
        gated
        reasons={["success_rate: higher-is-better regression of 40.0% (limit 10%)"]}
        resultId="res-1"
        metrics={[
          line({
            candidate_value: 0.6,
            relative_delta: -0.4,
            adverse_change: 0.4,
            regression: true,
            gate_outcome: "regression",
          }),
        ]}
        advisories={[]}
        evidence={[evidence({})]}
      />,
    );

    expect(screen.getByText("BLOCK")).toBeInTheDocument();
    expect(
      screen.getByText("Reliability regressed 40%; policy allows up to 10%."),
    ).toBeInTheDocument();
    // per-metric status honours gate_outcome
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    // compact evidence: sample count, baseline -> candidate, change, 95% CI, status
    const evidenceSection = screen
      .getByText(/Statistical evidence/i)
      .closest("div") as HTMLElement;
    expect(within(evidenceSection).getByText(/8 paired samples/)).toBeInTheDocument();
    expect(within(evidenceSection).getByText(/1\.000 → 0\.600/)).toBeInTheDocument();
    expect(within(evidenceSection).getByText(/-40%/)).toBeInTheDocument();
    expect(
      within(evidenceSection).getByText(/95% CI \[-0\.500, -0\.300\]/),
    ).toBeInTheDocument();
    expect(
      within(evidenceSection).getByText("CI supports a regression"),
    ).toBeInTheDocument();
    // no "unverified concerns" caveat on a real BLOCK
    expect(screen.queryByText(/unverified concerns/i)).not.toBeInTheDocument();
  });

  it("shows a PASS with an insufficient-evidence advisory that is not a safe pass", () => {
    render(
      <ReleaseDecision
        decision="pass"
        gated
        reasons={[]}
        resultId="res-2"
        metrics={[
          line({
            candidate_value: 0,
            relative_delta: -1,
            threshold: 0,
            adverse_change: 1,
            regression: false,
            gate_outcome: "regression_low_evidence",
          }),
        ]}
        advisories={[
          "success_rate: observed higher-is-better regression of 100.0% exceeds the 0% limit, but only 2 paired sample(s) (minimum 8) -- insufficient evidence to block; increase repeats or dataset size",
        ]}
        evidence={[
          evidence({
            n_pairs: 2,
            candidate: { n: 2, mean: 0, median: 0, stdev: 0 },
            paired_delta: { n: 2, mean: -1, median: -1, stdev: 0 },
            delta: -1,
            relative_change: -1,
            ci_low: null,
            ci_high: null,
            ci_excludes_zero: false,
            insufficient_evidence: true,
          }),
        ]}
      />,
    );

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/with unverified concerns/i)).toBeInTheDocument();
    expect(screen.getByText(/Do not read this as an unconditional pass/i)).toBeInTheDocument();
    // advisory text is shown in the caveat callout (and again in raw gate output)
    expect(
      screen.getAllByText(/insufficient evidence to block/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Breach — low evidence")).toBeInTheDocument();
    const evidenceSection = screen
      .getByText(/Statistical evidence/i)
      .closest("div") as HTMLElement;
    expect(within(evidenceSection).getByText(/2 paired samples/)).toBeInTheDocument();
    expect(within(evidenceSection).getByText(/95% CI not computed/)).toBeInTheDocument();
    expect(
      within(evidenceSection).getByText("Insufficient evidence"),
    ).toBeInTheDocument();
  });

  it("shows a PASS with an inconclusive-evidence advisory", () => {
    render(
      <ReleaseDecision
        decision="pass"
        gated
        reasons={[]}
        resultId="res-3"
        metrics={[
          line({
            metric: "latency_ms.mean",
            direction: "lower_is_better",
            baseline_value: 40,
            candidate_value: 90,
            relative_delta: 1.25,
            threshold: 0.2,
            adverse_change: 1.25,
            regression: false,
            gate_outcome: "regression_inconclusive",
          }),
        ]}
        advisories={[
          "latency_ms.mean: observed lower-is-better regression of 125.0% exceeds the 20% limit, but the 95% CI [-5, 120] does not confirm a regression beyond the tolerated boundary -- not blocking",
        ]}
        evidence={[
          evidence({
            metric: "latency_ms.mean",
            kind: "continuous",
            baseline: { n: 8, mean: 40, median: 40, stdev: 3 },
            candidate: { n: 8, mean: 90, median: 90, stdev: 8 },
            paired_delta: { n: 8, mean: 50, median: 50, stdev: 30 },
            delta: 50,
            relative_change: 1.25,
            ci_low: -5,
            ci_high: 120,
            ci_excludes_zero: false,
          }),
        ]}
      />,
    );

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/with unverified concerns/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/does not confirm a regression/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Breach — inconclusive")).toBeInTheDocument();
    const evidenceSection = screen
      .getByText(/Statistical evidence/i)
      .closest("div") as HTMLElement;
    expect(within(evidenceSection).getByText("Inconclusive")).toBeInTheDocument();
    expect(
      within(evidenceSection).getByText(/40\.0 ms → 90\.0 ms/),
    ).toBeInTheDocument();
    expect(
      within(evidenceSection).getByText(/95% CI \[-5\.0 ms, 120\.0 ms\]/),
    ).toBeInTheDocument();
  });

  it("renders a clean PASS with no advisory and no caveat badge", () => {
    render(
      <ReleaseDecision
        decision="pass"
        gated
        reasons={[]}
        resultId="res-4"
        metrics={[line({ candidate_value: 1, relative_delta: 0.05, adverse_change: -0.05 })]}
        advisories={[]}
        evidence={[evidence({ candidate: { n: 8, mean: 1, median: 1, stdev: 0 }, delta: 0 })]}
      />,
    );

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.queryByText(/unverified concerns/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/All gated metrics stayed within the release policy/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Do not read this as an unconditional pass/i)).not.toBeInTheDocument();
  });

  it("keeps deterministic (point-only) metrics understandable without a fake CI", () => {
    render(
      <ReleaseDecision
        decision="block"
        gated
        reasons={["latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)"]}
        resultId="res-5"
        metrics={[
          line({
            metric: "success_rate",
            candidate_value: 1,
            relative_delta: 0,
            adverse_change: 0,
            gate_outcome: "pass",
          }),
          line({
            metric: "latency_ms.p95",
            direction: "lower_is_better",
            baseline_value: 100,
            candidate_value: 150,
            relative_delta: 0.5,
            threshold: 0.2,
            adverse_change: 0.5,
            regression: true,
            gate_outcome: "regression",
          }),
        ]}
        advisories={[]}
        evidence={[evidence({ metric: "success_rate", ci_low: -0.02, ci_high: 0.02 })]}
      />,
    );

    // p95 shows in the metric table as Blocked...
    expect(screen.getByText("P95 latency")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    // ...but is explicitly called out as point-only, and gets no evidence row
    expect(
      screen.getByText(/gated on the point comparison only/i),
    ).toBeInTheDocument();
    const evidenceSection = screen
      .getByText(/Statistical evidence/i)
      .closest("div") as HTMLElement;
    expect(within(evidenceSection).queryByText("P95 latency")).not.toBeInTheDocument();
    expect(within(evidenceSection).getByText("Reliability")).toBeInTheDocument();
  });

  it("tolerates an older API response with no evidence or advisories", () => {
    render(
      <ReleaseDecision
        decision="pass"
        gated
        reasons={[]}
        resultId="res-6"
        metrics={[line({ relative_delta: 0.02, adverse_change: -0.02 })]}
      />,
    );

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.queryByText(/Statistical evidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unverified concerns/i)).not.toBeInTheDocument();
  });
});
