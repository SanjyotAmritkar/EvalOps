import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProductionTracesPage from "@/app/projects/[projectId]/traces/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
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

const V1 = {
  id: "v1",
  project_id: "p1",
  name: "support-prompt",
  version: "v1",
  provider: "ollama",
  model: "llama3.2",
  prompt_template: "Q: ${input}",
  parameters: {},
  rag_config: null,
  tool_policy: null,
  created_at: "2026-09-08T12:00:00Z",
};

const TRACE_OK = {
  id: "t1",
  project_id: "p1",
  system_version_id: "v1",
  created_at: "2026-09-08T12:00:00Z",
  input: "How do I reset my password?",
  output: "Use the reset link on the login page.",
  reference_output: "Click 'Forgot password'.",
  metadata: { conversation_id: "c-1" },
  latency_ms: 812,
  cost_usd: 0.0004,
  error: null,
  origin: "production",
};

const TRACE_ERR = {
  ...TRACE_OK,
  id: "t2",
  input: "What is my balance?",
  output: "",
  reference_output: null,
  metadata: {},
  latency_ms: null,
  cost_usd: null,
  error: "provider timeout after 30s",
};

function routeFetch(
  overrides: {
    traces?: unknown;
    versions?: unknown;
    traceById?: Record<string, unknown>;
    promoteStatus?: number;
    promoteBody?: unknown;
  } = {},
) {
  return vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "POST" && url.endsWith("/trace-datasets")) {
      return Promise.resolve(
        jsonResponse(
          overrides.promoteBody ?? {
            id: "ds9",
            project_id: "p1",
            name: "production-regression-set",
            version: 1,
            created_at: "2026-09-09T10:00:00Z",
            cases: [
              {
                id: "c1",
                input: TRACE_OK.input,
                expected_output: "Click 'Forgot password'.",
                origin: "promoted_trace",
                source_trace_id: "t1",
              },
              {
                id: "c2",
                input: TRACE_ERR.input,
                expected_output: null,
                origin: "promoted_trace",
                source_trace_id: "t2",
              },
            ],
          },
          overrides.promoteStatus ?? 201,
        ),
      );
    }
    if (url.endsWith("/projects/p1/traces")) {
      return Promise.resolve(
        jsonResponse(overrides.traces ?? [TRACE_OK, TRACE_ERR]),
      );
    }
    if (url.endsWith("/projects/p1/system-versions")) {
      return Promise.resolve(jsonResponse(overrides.versions ?? [V1]));
    }
    const byId = url.match(/\/api\/traces\/(\w+)$/);
    if (byId) {
      const map: Record<string, unknown> = overrides.traceById ?? {
        t1: TRACE_OK,
        t2: TRACE_ERR,
      };
      return Promise.resolve(jsonResponse(map[byId[1]!]));
    }
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

describe("ProductionTracesPage", () => {
  it("renders the trace list with existing fields and error vs output status", async () => {
    vi.stubGlobal("fetch", routeFetch());
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    const okRow = (
      await screen.findByText("How do I reset my password?")
    ).closest("tr")!;
    expect(within(okRow).getByText("output")).toBeInTheDocument();
    expect(within(okRow).getByText("yes")).toBeInTheDocument(); // reference available
    expect(okRow).toHaveTextContent("support-prompt v1"); // resolved system version
    expect(okRow).toHaveTextContent("812 ms");
    expect(okRow).toHaveTextContent("$0.0004");

    const errRow = screen.getByText("What is my balance?").closest("tr")!;
    expect(within(errRow).getByText("error")).toBeInTheDocument();
    // reference-less trace shows a dash, not a fabricated reference
    expect(within(errRow).queryByText("yes")).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no traces", async () => {
    vi.stubGlobal("fetch", routeFetch({ traces: [] }));
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    expect(
      await screen.findByText("No production traces yet"),
    ).toBeInTheDocument();
  });

  it("shows an error state when the traces API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "boom" }, 500)),
    );
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("Could not load traces")).toBeInTheDocument();
  });

  it("inspects a trace and shows provenance with production output marked as not ground truth", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const user = userEvent.setup();
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    await screen.findByText("How do I reset my password?");
    await user.click(screen.getAllByRole("button", { name: "Inspect" })[0]!);

    const detail = await screen.findByRole("region", { name: "Trace detail" });
    expect(within(detail).getByText("t1")).toBeInTheDocument(); // trace id / provenance
    expect(detail).toHaveTextContent(/not\s+evaluation ground truth/i);
    expect(detail).toHaveTextContent("Production output");
    expect(
      within(detail).getByText("Use the reset link on the login page."),
    ).toBeInTheDocument();
    // metadata is shown
    expect(within(detail).getByText(/conversation_id/)).toBeInTheDocument();
  });

  it("selecting traces shows reference coverage and the reference-less warning", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const user = userEvent.setup();
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    await screen.findByText("How do I reset my password?");
    const checkboxes = screen.getAllByRole("checkbox", {
      name: /Select trace/,
    });
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);

    expect(screen.getByText("2 traces selected")).toBeInTheDocument();
    expect(
      screen.getByText("1 of 2 selected traces have reference outputs."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/reference-based evaluators may not be applicable/i),
    ).toBeInTheDocument();
  });

  it("promotes selected traces and links into the dataset and experiment flow", async () => {
    const fetchMock = routeFetch();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    await screen.findByText("How do I reset my password?");
    const checkboxes = screen.getAllByRole("checkbox", {
      name: /Select trace/,
    });
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);

    await user.type(
      screen.getByLabelText("Replay dataset name"),
      "production-regression-set",
    );
    await user.click(
      screen.getByRole("button", { name: "Create replay dataset" }),
    );

    expect(
      await screen.findByText("Replay dataset created"),
    ).toBeInTheDocument();

    const post = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/projects/p1/trace-datasets");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({
      name: "production-regression-set",
      trace_ids: ["t1", "t2"],
    });

    const viewDataset = screen.getByRole("link", { name: "View dataset" });
    expect(viewDataset).toHaveAttribute("href", "/projects/p1/datasets/ds9");
    const createExperiment = screen.getByRole("link", {
      name: /Create experiment with this dataset/,
    });
    expect(createExperiment).toHaveAttribute(
      "href",
      "/projects/p1/experiments?dataset=ds9",
    );
  });

  it("explains a 409 name conflict without blocking", async () => {
    vi.stubGlobal(
      "fetch",
      routeFetch({
        promoteStatus: 409,
        promoteBody: { detail: "dataset conflicts with an existing record" },
      }),
    );
    const user = userEvent.setup();
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    await screen.findByText("How do I reset my password?");
    await user.click(
      screen.getAllByRole("checkbox", { name: /Select trace/ })[0]!,
    );
    await user.type(screen.getByLabelText("Replay dataset name"), "taken");
    await user.click(
      screen.getByRole("button", { name: "Create replay dataset" }),
    );

    expect(
      await screen.findByText(/already exists in this project/i),
    ).toBeInTheDocument();
  });

  it("adds a trace through the secondary form using only explicit fields", async () => {
    const fetchMock = routeFetch();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ProductionTracesPage />, { wrapper: makeWrapper() });

    await screen.findByText("How do I reset my password?");
    await user.click(screen.getByRole("button", { name: "Add trace" }));

    await user.selectOptions(
      await screen.findByLabelText("System version"),
      "v1",
    );
    await user.type(screen.getByLabelText("Input"), "New question?");
    await user.type(
      screen.getByLabelText(/Production output/),
      "Some answer",
    );
    await user.click(screen.getByRole("button", { name: "Add trace" }));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        (call) =>
          (call[1] as RequestInit | undefined)?.method === "POST" &&
          String(call[0]).endsWith("/projects/p1/traces"),
      );
      expect(post).toBeTruthy();
      expect(
        JSON.parse((post![1] as RequestInit).body as string),
      ).toEqual({
        system_version_id: "v1",
        input: "New question?",
        output: "Some answer",
      });
    });
  });
});
