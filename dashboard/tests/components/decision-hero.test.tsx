import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { DecisionHero } from "@/app/projects/[projectId]/experiments/[experimentId]/decision-hero";
import type { MetricLine } from "@/lib/api/types";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

function line(overrides: Partial<MetricLine>): MetricLine {
  return {
    metric: "contains.pass_rate",
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

describe("DecisionHero", () => {
  it("renders a clean PASS as Ready to release", () => {
    render(
      <DecisionHero
        decision="pass"
        gated
        reasons={[]}
        advisories={[]}
        metrics={[line({ relative_delta: 0.05, adverse_change: -0.05 })]}
        policyHref="/p"
      />,
    );
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("Ready to release")).toBeInTheDocument();
    expect(
      screen.getByText(/All gated metrics stayed within the release policy/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/advisory/i)).not.toBeInTheDocument();
  });

  it("renders a BLOCK with the count and the backend's blocking sentences", () => {
    render(
      <DecisionHero
        decision="block"
        gated
        reasons={["contains.pass_rate: higher-is-better regression of 50.0% (limit 10%)"]}
        advisories={[]}
        metrics={[
          line({
            candidate_value: 0.5,
            relative_delta: -0.5,
            adverse_change: 0.5,
            regression: true,
            gate_outcome: "regression",
          }),
        ]}
        policyHref="/p"
      />,
    );
    expect(screen.getByText("BLOCK")).toBeInTheDocument();
    expect(screen.getByText("Release blocked")).toBeInTheDocument();
    expect(screen.getByText(/1 policy metric regressed beyond tolerance/i)).toBeInTheDocument();
    expect(
      screen.getByText("Answer quality regressed 50%; policy allows up to 10%."),
    ).toBeInTheDocument();
  });

  it("distinguishes a PASS-with-advisory from a clean pass", () => {
    render(
      <DecisionHero
        decision="pass"
        gated
        reasons={[]}
        advisories={[
          "contains.pass_rate: observed regression of 30% exceeds the 10% limit, but only 3 paired sample(s) -- insufficient evidence to block",
        ]}
        metrics={[
          line({
            candidate_value: 0.7,
            adverse_change: 0.3,
            regression: false,
            gate_outcome: "regression_low_evidence",
          }),
        ]}
        policyHref="/p"
      />,
    );
    expect(screen.getByText("Passed with unverified concerns")).toBeInTheDocument();
    expect(screen.getByText(/advisory/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Do not read this as an unconditional pass/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/insufficient evidence to block/i)).toBeInTheDocument();
  });

  it("renders an ungated run as Comparison only with a path to release policies", () => {
    render(
      <DecisionHero
        decision="pass"
        gated={false}
        reasons={[]}
        advisories={[]}
        metrics={[line({})]}
        policyHref="/projects/p1/release-policies"
      />,
    );
    expect(screen.getByText("Not gated")).toBeInTheDocument();
    expect(screen.getByText("Comparison only")).toBeInTheDocument();
    expect(screen.getByText(/no PASS or BLOCK decision was made/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /attach a release policy/i }),
    ).toHaveAttribute("href", "/projects/p1/release-policies");
  });
});
