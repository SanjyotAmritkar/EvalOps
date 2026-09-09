import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ExperimentsPage from "@/app/projects/[projectId]/experiments/page";
import { jsonResponse, makeWrapper } from "../test-utils";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  usePathname: () => "/projects/p1/experiments",
  useRouter: () => ({ push }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  push.mockReset();
});

const DATASET = {
  id: "d1",
  project_id: "p1",
  name: "support",
  version: 1,
  created_at: "2026-09-08T12:00:00Z",
  cases: [{ id: "c1", input: "a", expected_output: "1", origin: "authored", source_trace_id: null }],
};
const V1 = {
  id: "v1", project_id: "p1", name: "support-prompt", version: "v1",
  provider: "ollama", model: "llama3.2", prompt_template: "Q: ${input}",
  parameters: {}, rag_config: null, tool_policy: null,
  created_at: "2026-09-08T12:00:00Z",
};
const V2 = { ...V1, id: "v2", version: "v2" };
const EXPERIMENT = {
  id: "e1", project_id: "p1", dataset_id: "d1",
  baseline_version_id: "v1", candidate_version_id: "v2",
  repeats: 2, release_policy_id: null, created_at: "2026-09-08T13:00:00Z",
};

function routeFetch(overrides: Record<string, unknown> = {}) {
  return vi.fn((url: string) => {
    if (url.endsWith("/experiments")) return Promise.resolve(jsonResponse(overrides.experiments ?? [EXPERIMENT]));
    if (url.endsWith("/datasets")) return Promise.resolve(jsonResponse(overrides.datasets ?? [DATASET]));
    if (url.endsWith("/system-versions")) return Promise.resolve(jsonResponse(overrides.versions ?? [V1, V2]));
    if (url.endsWith("/release-policies")) return Promise.resolve(jsonResponse([]));
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

describe("ExperimentsPage", () => {
  it("renders experiments with resolved labels and a link into the detail page", async () => {
    vi.stubGlobal("fetch", routeFetch());
    render(<ExperimentsPage />, { wrapper: makeWrapper() });

    const link = await screen.findByRole("link", {
      name: /support-prompt v1.*support-prompt v2/,
    });
    expect(link).toHaveAttribute("href", "/projects/p1/experiments/e1");
    const row = link.closest("tr")!;
    expect(row).toHaveTextContent("support-prompt v1");
    expect(row).toHaveTextContent("support-prompt v2");
    expect(row).toHaveTextContent("support"); // dataset name column
  });

  it("toggles the creation form from the header action", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const user = userEvent.setup();
    render(<ExperimentsPage />, { wrapper: makeWrapper() });

    await screen.findByRole("link", {
      name: /support-prompt v1.*support-prompt v2/,
    });
    await user.click(screen.getByRole("button", { name: "New experiment" }));
    expect(await screen.findByLabelText("Dataset")).toBeInTheDocument();
  });

  it("explains when there are not enough resources to create an experiment", async () => {
    vi.stubGlobal("fetch", routeFetch({ experiments: [], versions: [V1] }));
    const user = userEvent.setup();
    render(<ExperimentsPage />, { wrapper: makeWrapper() });

    await screen.findByText("No experiments yet");
    await user.click(
      screen.getAllByRole("button", { name: /new experiment/i })[0]!,
    );
    expect(
      await screen.findByText(/Not enough resources to define an experiment/i),
    ).toBeInTheDocument();
  });
});
