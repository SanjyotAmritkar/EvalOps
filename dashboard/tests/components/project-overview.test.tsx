import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProjectOverviewPage from "@/app/projects/[projectId]/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  usePathname: () => "/projects/p1",
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const PROJECT = {
  id: "p1",
  name: "EvalOps Demo",
  created_at: "2026-09-08T12:00:00Z",
};

function stub(counts: {
  datasets: number;
  versions: number;
  experiments: unknown[];
  /** Per-experiment-id `GET /experiments/{id}/results` payload; an id with no
   * entry here answers with an empty array (not yet run). */
  results?: Record<string, unknown[]>;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/api/projects/p1"))
        return Promise.resolve(jsonResponse(PROJECT));
      if (url.endsWith("/datasets"))
        return Promise.resolve(
          jsonResponse(
            Array.from({ length: counts.datasets }, (_, i) => ({
              id: `d${i}`,
              name: `dataset-${i}`,
              cases: [],
            })),
          ),
        );
      if (url.endsWith("/system-versions"))
        return Promise.resolve(
          jsonResponse(
            Array.from({ length: counts.versions }, (_, i) => ({
              id: `v${i}`,
              name: "cfg",
              version: `v${i}`,
            })),
          ),
        );
      if (url.endsWith("/experiments"))
        return Promise.resolve(jsonResponse(counts.experiments));
      const resultsMatch = /\/experiments\/([^/]+)\/results$/.exec(url);
      if (resultsMatch) {
        const id = resultsMatch[1] as string;
        return Promise.resolve(jsonResponse(counts.results?.[id] ?? []));
      }
      return Promise.reject(new Error(`unexpected ${url}`));
    }),
  );
}

describe("ProjectOverviewPage", () => {
  it("shows a real setup checklist and the primary action when ready", async () => {
    stub({ datasets: 1, versions: 2, experiments: [] });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    // teaches the flow without an architecture lecture
    expect(screen.getByText("How it fits together")).toBeInTheDocument();
    expect(screen.getByText("Baseline")).toBeInTheDocument();
    expect(screen.getByText("Candidate")).toBeInTheDocument();
    expect(screen.getByText("Release decision")).toBeInTheDocument();

    // ready -> primary CTA is "Run evaluation"
    expect(
      await screen.findByRole("link", { name: "Run evaluation" }),
    ).toBeInTheDocument();

    // real, actionable setup state (not fabricated analytics)
    expect(
      screen.getByText(/1 added — manage datasets/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/2 added — manage system versions/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Run it and review the release decision"),
    ).toBeInTheDocument();
  });

  it("nudges toward the missing setup step when not ready", async () => {
    stub({ datasets: 0, versions: 1, experiments: [] });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    // not ready -> the primary action points at the first missing piece
    expect(
      await screen.findByRole("link", { name: "Add a dataset" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/1 of 2 — add system versions/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Run evaluation" }),
    ).not.toBeInTheDocument();
  });

  it("lists recent experiments from real data only, newest first", async () => {
    stub({
      datasets: 1,
      versions: 2,
      experiments: [
        {
          id: "e-old",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-01T00:00:00Z",
        },
        {
          id: "e-new",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-09T00:00:00Z",
        },
      ],
    });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    await waitFor(() =>
      expect(screen.getByText("Recent experiments")).toBeInTheDocument(),
    );
    const links = screen
      .getAllByRole("link")
      .filter((el) => el.getAttribute("href")?.includes("/experiments/"));
    expect(links[0]).toHaveAttribute(
      "href",
      "/projects/p1/experiments/e-new",
    );
  });

  function stepFourListItem(): HTMLElement {
    const title = screen.getByText("Run it and review the release decision");
    const li = title.closest("li");
    if (!li) throw new Error("step 4 list item not found");
    return li;
  }

  it("marks step 4 incomplete when experiments exist but none has a result yet", async () => {
    stub({
      datasets: 1,
      versions: 2,
      experiments: [
        {
          id: "e1",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-01T00:00:00Z",
        },
      ],
    });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    await screen.findByText("Run it and review the release decision");
    await waitFor(() => expect(stepFourListItem()).not.toHaveTextContent("✓"));
  });

  it("marks step 4 complete only once a persisted result exists — even on an older, non-recent experiment", async () => {
    // Four experiments: the completed result sits on the OLDEST one, which
    // falls outside the "Recent experiments" (top-3) slice below -- proving
    // the check considers every experiment, not just the recent few.
    stub({
      datasets: 1,
      versions: 2,
      experiments: [
        {
          id: "e-oldest-with-result",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-01T00:00:00Z",
        },
        {
          id: "e2",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-02T00:00:00Z",
        },
        {
          id: "e3",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-03T00:00:00Z",
        },
        {
          id: "e-newest",
          dataset_id: "d0",
          baseline_version_id: "v0",
          candidate_version_id: "v1",
          created_at: "2026-09-04T00:00:00Z",
        },
      ],
      results: {
        "e-oldest-with-result": [
          {
            id: "r1",
            experiment_id: "e-oldest-with-result",
            created_at: "2026-09-01T01:00:00Z",
            decision: "block",
            gated: true,
            reasons: ["latency_ms.p95: lower-is-better regression of 50.0% (limit 20%)"],
            metrics: [],
            advisories: [],
          },
        ],
      },
    });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    await screen.findByText("Run it and review the release decision");
    // recent-experiments slice only shows the 3 newest -- the completed one
    // is deliberately not among them
    await waitFor(() =>
      expect(screen.getByText("Recent experiments")).toBeInTheDocument(),
    );
    const recentHrefs = screen
      .getAllByRole("link")
      .map((el) => el.getAttribute("href"))
      .filter((href): href is string => href?.includes("/experiments/") ?? false);
    expect(recentHrefs).not.toContain(
      "/projects/p1/experiments/e-oldest-with-result",
    );
    expect(recentHrefs).toHaveLength(3);

    await waitFor(() => expect(stepFourListItem()).toHaveTextContent("✓"));
  });
});
