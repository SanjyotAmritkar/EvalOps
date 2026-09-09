import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExperimentForm } from "@/app/projects/[projectId]/experiments/experiment-form";
import { jsonResponse, makeWrapper } from "../test-utils";

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
  name: "support",
  version: 1,
  created_at: "2026-09-08T12:00:00Z",
  cases: [
    { id: "c1", input: "a", expected_output: "1", origin: "authored", source_trace_id: null },
    { id: "c2", input: "b", expected_output: "2", origin: "authored", source_trace_id: null },
  ],
};
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
const V2 = { ...V1, id: "v2", version: "v2" };
const POLICY = {
  id: "rp1",
  name: "demo-policy",
  thresholds: { "latency_ms.p95": 0.2 },
  max_safety_violations: 0,
};

function stubResources() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("/api/projects/p1/datasets"))
        return Promise.resolve(jsonResponse([DATASET]));
      if (url.endsWith("/api/projects/p1/system-versions"))
        return Promise.resolve(jsonResponse([V1, V2]));
      if (url.endsWith("/api/release-policies"))
        return Promise.resolve(jsonResponse([POLICY]));
      return Promise.reject(new Error(`unexpected ${url}`));
    }),
  );
}

describe("ExperimentForm", () => {
  it("shows resolved names in the version selectors", async () => {
    stubResources();
    render(<ExperimentForm projectId="p1" onCreated={vi.fn()} />, {
      wrapper: makeWrapper(),
    });

    const baseline = await screen.findByLabelText("Baseline system version");
    await waitFor(() =>
      expect(within(baseline).getAllByRole("option").length).toBe(3),
    );
    // resolved labels: name, version, and provider/model — not the raw id
    expect(baseline).toHaveTextContent("support-prompt v1");
    expect(baseline).toHaveTextContent("support-prompt v2");
    expect(baseline).toHaveTextContent("ollama/llama3.2");
  });

  it("blocks submit when baseline and candidate are the same", async () => {
    stubResources();
    const user = userEvent.setup();
    render(<ExperimentForm projectId="p1" onCreated={vi.fn()} />, {
      wrapper: makeWrapper(),
    });

    await screen.findByRole("option", { name: /support v1 · 2 cases/ });
    await user.selectOptions(screen.getByLabelText("Dataset"), "d1");
    await user.selectOptions(
      screen.getByLabelText("Baseline system version"),
      "v1",
    );
    await user.selectOptions(
      screen.getByLabelText("Candidate system version"),
      "v1",
    );

    expect(
      screen.getByText(/must be different system versions/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create experiment" }),
    ).toBeDisabled();
  });

  it("creates an experiment and calls onCreated with the result", async () => {
    stubResources();
    const created = {
      id: "e9",
      project_id: "p1",
      dataset_id: "d1",
      baseline_version_id: "v1",
      candidate_version_id: "v2",
      repeats: 1,
      release_policy_id: null,
      created_at: "2026-09-08T13:00:00Z",
    };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST")
        return Promise.resolve(jsonResponse(created, 201));
      if (url.endsWith("/datasets")) return Promise.resolve(jsonResponse([DATASET]));
      if (url.endsWith("/system-versions"))
        return Promise.resolve(jsonResponse([V1, V2]));
      if (url.endsWith("/release-policies"))
        return Promise.resolve(jsonResponse([POLICY]));
      return Promise.reject(new Error(url));
    });
    vi.stubGlobal("fetch", fetchMock);

    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<ExperimentForm projectId="p1" onCreated={onCreated} />, {
      wrapper: makeWrapper(),
    });

    await screen.findByRole("option", { name: /support v1 · 2 cases/ });
    await user.selectOptions(screen.getByLabelText("Dataset"), "d1");
    await user.selectOptions(
      screen.getByLabelText("Baseline system version"),
      "v1",
    );
    await user.selectOptions(
      screen.getByLabelText("Candidate system version"),
      "v2",
    );

    const submit = screen.getByRole("button", { name: "Create experiment" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));

    const post = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/projects/p1/experiments");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({
      dataset_id: "d1",
      baseline_version_id: "v1",
      candidate_version_id: "v2",
      release_policy_id: null,
      repeats: 1,
    });
  });
});
