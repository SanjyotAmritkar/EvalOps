import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useProjectHasCompletedResult } from "@/lib/query/experiments";
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

/** Routes `GET /experiments/{id}/results` per experiment id to the given
 * results (or a rejection), keyed by the id embedded in the URL. */
function stubResultsByExperiment(
  byId: Record<string, EvaluationResult[] | "error">,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const match = /\/experiments\/([^/]+)\/results$/.exec(url);
      const id = match?.[1];
      const entry = id ? byId[id] : undefined;
      if (entry === "error" || entry === undefined) {
        return Promise.reject(new Error(`no stub for ${url}`));
      }
      return Promise.resolve(jsonResponse(entry));
    }),
  );
}

describe("useProjectHasCompletedResult", () => {
  it("is false, not pending, for zero experiments", () => {
    stubResultsByExperiment({});
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult([]),
      { wrapper: makeWrapper() },
    );
    expect(hook.current.isPending).toBe(false);
    expect(hook.current.hasCompletedResult).toBe(false);
  });

  it("is false while every experiment has an empty results array", async () => {
    stubResultsByExperiment({ e1: [], e2: [] });
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult(["e1", "e2"]),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(hook.current.isPending).toBe(false));
    expect(hook.current.hasCompletedResult).toBe(false);
  });

  it("is true when a non-recent (not-first, not-last) experiment has a completed result", async () => {
    stubResultsByExperiment({
      "e-newest": [],
      "e-middle-with-result": [result({ decision: "pass" })],
      "e-oldest": [],
    });
    const { result: hook } = renderHook(
      () =>
        useProjectHasCompletedResult([
          "e-newest",
          "e-middle-with-result",
          "e-oldest",
        ]),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(hook.current.isPending).toBe(false));
    expect(hook.current.hasCompletedResult).toBe(true);
  });

  it("counts a BLOCK result as completed", async () => {
    stubResultsByExperiment({ e1: [result({ decision: "block" })] });
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult(["e1"]),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(hook.current.isPending).toBe(false));
    expect(hook.current.hasCompletedResult).toBe(true);
  });

  it("counts a PASS-with-advisory result as completed", async () => {
    stubResultsByExperiment({
      e1: [result({ decision: "pass", advisories: ["low evidence"] })],
    });
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult(["e1"]),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(hook.current.isPending).toBe(false));
    expect(hook.current.hasCompletedResult).toBe(true);
  });

  it("treats an API error the same as no result, not a completed one", async () => {
    stubResultsByExperiment({ e1: "error" });
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult(["e1"]),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(hook.current.isPending).toBe(false));
    expect(hook.current.hasCompletedResult).toBe(false);
  });

  it("stays pending (never a false positive) while a query is still loading", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})), // never resolves
    );
    const { result: hook } = renderHook(
      () => useProjectHasCompletedResult(["e1"]),
      { wrapper: makeWrapper() },
    );
    expect(hook.current.isPending).toBe(true);
    expect(hook.current.hasCompletedResult).toBe(false);
  });
});
