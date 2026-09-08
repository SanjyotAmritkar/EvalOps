import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DatasetsPage from "@/app/projects/[projectId]/datasets/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  usePathname: () => "/projects/p1/datasets",
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

const DATASET = {
  id: "d1",
  project_id: "p1",
  name: "support-golden",
  version: 1,
  created_at: "2026-09-08T12:00:00Z",
  cases: [
    { id: "c1", input: "a", expected_output: "1", origin: "authored", source_trace_id: null },
    { id: "c2", input: "b", expected_output: null, origin: "authored", source_trace_id: null },
  ],
};

describe("DatasetsPage", () => {
  it("lists datasets with their case counts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([DATASET])));

    render(<DatasetsPage />, { wrapper: makeWrapper() });

    const link = await screen.findByRole("link", { name: "support-golden" });
    expect(link).toHaveAttribute("href", "/projects/p1/datasets/d1");
    const row = link.closest("tr")!;
    expect(row).toHaveTextContent("v1");
    expect(row).toHaveTextContent("2");
  });

  it("validates pasted JSONL and creates a dataset from the parsed cases", async () => {
    const created = { ...DATASET, id: "d2", name: "new-set" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(created, 201))
      .mockResolvedValue(jsonResponse([created]));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<DatasetsPage />, { wrapper: makeWrapper() });

    await screen.findByText("No datasets yet");
    await user.click(screen.getAllByRole("button", { name: /new dataset/i })[0]!);

    await user.type(screen.getByLabelText("Name"), "new-set");

    const jsonl = screen.getByLabelText("Cases (JSONL)");
    await user.click(jsonl);
    await user.paste("not json");
    expect(await screen.findByText(/Line 1: not valid JSON/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create dataset" }),
    ).toBeDisabled();

    await user.clear(jsonl);
    await user.click(jsonl);
    await user.paste(
      '{"input": "q1", "expected_output": "a1"}\n{"input": "q2"}',
    );
    expect(screen.getByText(/2 cases parsed/)).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: "Create dataset" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    expect(await screen.findByRole("link", { name: "new-set" })).toBeInTheDocument();

    const post = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/projects/p1/datasets");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({
      name: "new-set",
      version: 1,
      cases: [{ input: "q1", expected_output: "a1" }, { input: "q2" }],
    });
  });

  it("explains a 409 conflict in product terms", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({ detail: "dataset already exists" }, 409),
      );
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<DatasetsPage />, { wrapper: makeWrapper() });

    await screen.findByText("No datasets yet");
    await user.click(screen.getAllByRole("button", { name: /new dataset/i })[0]!);
    await user.type(screen.getByLabelText("Name"), "support-golden");
    await user.click(screen.getByLabelText("Cases (JSONL)"));
    await user.paste('{"input": "q1"}');

    await user.click(screen.getByRole("button", { name: "Create dataset" }));

    expect(
      await screen.findByText(/already exists in this project/i),
    ).toBeInTheDocument();
  });
});
