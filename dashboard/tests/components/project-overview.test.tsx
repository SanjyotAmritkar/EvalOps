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

function stub(counts: { datasets: number; versions: number; experiments: number }) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/api/projects/p1")) return Promise.resolve(jsonResponse(PROJECT));
      if (url.endsWith("/datasets"))
        return Promise.resolve(jsonResponse(Array.from({ length: counts.datasets }, (_, i) => ({ id: `d${i}`, cases: [] }))));
      if (url.endsWith("/system-versions"))
        return Promise.resolve(jsonResponse(Array.from({ length: counts.versions }, (_, i) => ({ id: `v${i}` }))));
      if (url.endsWith("/experiments"))
        return Promise.resolve(jsonResponse(Array.from({ length: counts.experiments }, (_, i) => ({ id: `e${i}` }))));
      return Promise.reject(new Error(`unexpected ${url}`));
    }),
  );
}

describe("ProjectOverviewPage", () => {
  it("explains the workflow and shows real resource counts", async () => {
    stub({ datasets: 1, versions: 2, experiments: 3 });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    expect(
      screen.getByText(/applies a release policy to decide/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Baseline")).toBeInTheDocument();
    expect(screen.getByText("Candidate")).toBeInTheDocument();
    expect(screen.getByText("Release decision")).toBeInTheDocument();

    // resources exist -> the primary next action is offered
    expect(
      await screen.findByRole("link", { name: "Run evaluation" }),
    ).toBeInTheDocument();

    // counts come from the list endpoints, not fabricated
    await waitFor(() => {
      const tile = screen.getByText("Experiments").closest("a");
      expect(tile).toHaveTextContent("3");
    });
  });

  it("shows a workflow-oriented empty state when the project has nothing", async () => {
    stub({ datasets: 0, versions: 0, experiments: 0 });
    render(<ProjectOverviewPage />, { wrapper: makeWrapper() });

    expect(
      await screen.findByText("Nothing to evaluate yet"),
    ).toBeInTheDocument();
  });
});
