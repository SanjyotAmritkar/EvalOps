import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionBadge } from "@/components/decision-badge";
import type { EvaluationResult } from "@/lib/api/types";
import { jsonResponse, makeWrapper } from "../test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function result(overrides: Partial<EvaluationResult>): EvaluationResult {
  return {
    id: "r1",
    experiment_id: "e1",
    created_at: "2026-09-08T12:00:00Z",
    decision: "pass",
    gated: true,
    reasons: [],
    metrics: [],
    advisories: [],
    ...overrides,
  };
}

function stubResults(results: EvaluationResult[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(jsonResponse(results))),
  );
}

describe("DecisionBadge (CP 10.6B: list-level decision visibility)", () => {
  it("shows PASS for a clean pass", async () => {
    stubResults([result({ decision: "pass", advisories: [] })]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("PASS")).toBeInTheDocument();
  });

  it("shows BLOCK for a block decision", async () => {
    stubResults([result({ decision: "block" })]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("BLOCK")).toBeInTheDocument();
  });

  it("distinguishes a pass-with-advisory from a clean pass", async () => {
    stubResults([result({ decision: "pass", advisories: ["breach, low evidence"] })]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("PASS · advisory")).toBeInTheDocument();
  });

  it("shows Not gated for an ungated comparison", async () => {
    stubResults([result({ gated: false })]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("Not gated")).toBeInTheDocument();
  });

  it("shows Not run yet when no result is stored", async () => {
    stubResults([]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("Not run yet")).toBeInTheDocument();
  });

  it("uses the latest result when more than one is stored", async () => {
    stubResults([
      result({ id: "old", decision: "block" }),
      result({ id: "new", decision: "pass", advisories: [] }),
    ]);
    render(<DecisionBadge experimentId="e1" />, { wrapper: makeWrapper() });
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.queryByText("BLOCK")).not.toBeInTheDocument();
  });

  it("renders nothing while pending or on error, never a misleading placeholder", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network down"))),
    );
    const { container } = render(<DecisionBadge experimentId="e1" />, {
      wrapper: makeWrapper(),
    });
    expect(container).toBeEmptyDOMElement();
  });
});
