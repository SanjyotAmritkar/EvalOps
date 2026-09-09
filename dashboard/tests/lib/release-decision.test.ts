import { describe, expect, it } from "vitest";
import type { MetricLine } from "@/lib/api/types";
import {
  METRIC_STATUS_LABEL,
  blockingSentence,
  metricStatus,
} from "@/lib/release-decision";

function line(overrides: Partial<MetricLine>): MetricLine {
  return {
    metric: "success_rate",
    baseline_value: 1,
    candidate_value: 1,
    delta: 0,
    relative_delta: 0,
    direction: "higher_is_better",
    threshold: null,
    adverse_change: 0,
    regression: false,
    ...overrides,
  };
}

describe("metricStatus", () => {
  it("classifies a gated regression as blocked", () => {
    expect(metricStatus(line({ regression: true, adverse_change: 0.5, threshold: 0.1 }))).toBe(
      "blocked",
    );
  });

  it("classifies a favourable move as improved", () => {
    expect(metricStatus(line({ adverse_change: -0.2 }))).toBe("improved");
  });

  it("classifies an adverse move inside a threshold as within-threshold", () => {
    expect(metricStatus(line({ adverse_change: 0.05, threshold: 0.1 }))).toBe(
      "within-threshold",
    );
  });

  it("classifies an ungated adverse move as a plain regression", () => {
    expect(metricStatus(line({ adverse_change: 0.05, threshold: null }))).toBe(
      "regression",
    );
  });

  it("classifies no movement as unchanged", () => {
    expect(metricStatus(line({ adverse_change: 0 }))).toBe("unchanged");
  });

  it("classifies an unbounded non-blocking move as n/a", () => {
    expect(metricStatus(line({ adverse_change: null, regression: false }))).toBe("n/a");
  });

  it("has a label for every status", () => {
    expect(METRIC_STATUS_LABEL.blocked).toBe("Blocked");
    expect(METRIC_STATUS_LABEL.improved).toBe("Improved");
  });
});

describe("blockingSentence", () => {
  it("builds the friendly sentence from backend numbers", () => {
    expect(
      blockingSentence(
        line({
          metric: "contains.pass_rate",
          adverse_change: 0.5,
          threshold: 0.1,
          regression: true,
        }),
      ),
    ).toBe("Answer quality regressed 50%; policy allows up to 10%.");
  });

  it("handles an unbounded (zero-baseline) regression", () => {
    expect(
      blockingSentence(
        line({
          metric: "latency_ms.p95",
          adverse_change: null,
          threshold: 0.2,
          regression: true,
        }),
      ),
    ).toContain("zero baseline");
  });
});
