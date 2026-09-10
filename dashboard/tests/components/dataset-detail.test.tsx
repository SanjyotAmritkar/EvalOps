import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DatasetDetailPage from "@/app/projects/[projectId]/datasets/[datasetId]/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1", datasetId: "d1" }),
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

function caseOf(over: Record<string, unknown>) {
  return {
    id: "c",
    input: "q",
    expected_output: null,
    origin: "authored",
    source_trace_id: null,
    expected_retrieval_ids: [],
    expected_tool_calls: [],
    ...over,
  };
}

function dataset(cases: unknown[]) {
  return {
    id: "d1",
    project_id: "p1",
    name: "support",
    version: 1,
    created_at: "2026-09-08T12:00:00Z",
    cases,
  };
}

describe("DatasetDetailPage — RAG & agent expectations", () => {
  it("a plain case shows no expectations block", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          dataset([caseOf({ id: "c1", input: "plain", expected_output: "x" })]),
        ),
      ),
    );
    render(<DatasetDetailPage />, { wrapper: makeWrapper() });

    await screen.findByText("plain");
    expect(screen.queryByText("Retrieval expectations")).not.toBeInTheDocument();
    expect(screen.queryByText("Tool expectations")).not.toBeInTheDocument();
  });

  it("shows retrieval and tool expectations, tools in order incl. name-only", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          dataset([
            caseOf({
              id: "c1",
              input: "rag+agent case",
              expected_retrieval_ids: ["kb-1", "kb-2"],
              expected_tool_calls: [
                { name: "search", arguments: { q: "x" } },
                { name: "summarize", arguments: null },
              ],
            }),
          ]),
        ),
      ),
    );
    render(<DatasetDetailPage />, { wrapper: makeWrapper() });

    await screen.findByText("rag+agent case");

    const retrieval = screen
      .getByText(/Retrieval expectations/)
      .closest("details")!;
    expect(within(retrieval).getByText("kb-1")).toBeInTheDocument();
    expect(within(retrieval).getByText("kb-2")).toBeInTheDocument();

    const tools = screen.getByText(/Tool expectations/).closest("details")!;
    const items = within(tools).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("1.");
    expect(items[0]).toHaveTextContent("search");
    expect(items[0]).toHaveTextContent('{"q":"x"}');
    expect(items[1]).toHaveTextContent("2.");
    expect(items[1]).toHaveTextContent("summarize");
    expect(items[1]).toHaveTextContent("(name only)");
  });
});
