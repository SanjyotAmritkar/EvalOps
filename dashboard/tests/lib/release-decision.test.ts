import { describe, expect, it } from "vitest";
import type { MetricEvidence, MetricLine } from "@/lib/api/types";
import {
  EVIDENCE_STATUS_LABEL,
  METRIC_STATUS_LABEL,
  blockingSentence,
  evidenceStatus,
  metricDisplayStatus,
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

describe("metricDisplayStatus (CP 5.2 gate_outcome)", () => {
  it("maps a blocking regression to blocked", () => {
    expect(
      metricDisplayStatus(line({ gate_outcome: "regression", regression: true })),
    ).toBe("blocked");
  });

  it("keeps an inconclusive breach distinct from within-threshold", () => {
    const breach = line({
      gate_outcome: "regression_inconclusive",
      adverse_change: 0.4,
      threshold: 0.1,
      regression: false,
    });
    expect(metricDisplayStatus(breach)).toBe("breach-inconclusive");
    expect(metricStatus(breach)).toBe("within-threshold"); // the old view would mislead
  });

  it("maps a low-evidence breach to its own status", () => {
    expect(
      metricDisplayStatus(
        line({ gate_outcome: "regression_low_evidence", adverse_change: 1, threshold: 0 }),
      ),
    ).toBe("breach-low-evidence");
  });

  it("falls back to the point classification when gate_outcome is absent", () => {
    expect(metricDisplayStatus(line({ adverse_change: -0.2 }))).toBe("improved");
    expect(metricDisplayStatus(line({ gate_outcome: "pass", adverse_change: -0.2 }))).toBe(
      "improved",
    );
  });
});

describe("evidenceStatus", () => {
  it("reports insufficient when the backend flags it or gives no CI", () => {
    expect(evidenceStatus(evidence({ insufficient_evidence: true }), undefined)).toBe(
      "insufficient",
    );
    expect(
      evidenceStatus(evidence({ ci_low: null, ci_high: null }), line({})),
    ).toBe("insufficient");
  });

  it("mirrors the matching metric line's gate_outcome", () => {
    expect(
      evidenceStatus(evidence({}), line({ gate_outcome: "regression" })),
    ).toBe("supports-regression");
    expect(
      evidenceStatus(evidence({}), line({ gate_outcome: "regression_inconclusive" })),
    ).toBe("inconclusive");
    expect(evidenceStatus(evidence({}), line({ gate_outcome: "pass" }))).toBe(
      "within-tolerance",
    );
  });

  it("reads as reference-only when no gated metric line exists", () => {
    expect(evidenceStatus(evidence({ metric: "cost_usd.mean" }), undefined)).toBe(
      "reference-only",
    );
  });

  it("has a label for every evidence status", () => {
    expect(EVIDENCE_STATUS_LABEL["supports-regression"]).toBe("CI supports a regression");
    expect(EVIDENCE_STATUS_LABEL.insufficient).toBe("Insufficient evidence");
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
