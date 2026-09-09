import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ExperimentDetailPage from "@/app/projects/[projectId]/experiments/[experimentId]/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1", experimentId: "e1" }),
  usePathname: () => "/projects/p1/experiments/e1",
  useRouter: () => ({ push: vi.fn() }),
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

const EXPERIMENT = {
  id: "e1", project_id: "p1", dataset_id: "d1",
  baseline_version_id: "v1", candidate_version_id: "v2",
  repeats: 2, release_policy_id: "rp1", created_at: "2026-09-08T13:00:00Z",
};
const DATASET = {
  id: "d1", project_id: "p1", name: "support", version: 1,
  created_at: "2026-09-08T12:00:00Z",
  cases: [{ id: "c1", input: "a", expected_output: "1", origin: "authored", source_trace_id: null }],
};
const V1 = {
  id: "v1", project_id: "p1", name: "support-prompt", version: "v1",
  provider: "ollama", model: "llama3.2", prompt_template: "Q: ${input}",
  parameters: {}, rag_config: null, tool_policy: null, created_at: "2026-09-08T12:00:00Z",
};
const V2 = { ...V1, id: "v2", version: "v2" };
const POLICY = { id: "rp1", name: "demo-policy", thresholds: {}, max_safety_violations: 0 };

const PASS_RESPONSE = {
  evaluation_result_id: "res-1",
  experiment_id: "e1",
  dataset: "support",
  baseline: "support-prompt v1",
  candidate: "support-prompt v2",
  repeats: 2,
  counts: { cases: 1, runs: 4, failures: 0 },
  decision: "pass",
  gated: true,
  reasons: [],
  metrics: [
    {
      metric: "success_rate", baseline_value: 1, candidate_value: 1,
      delta: 0, relative_delta: 0, direction: "higher_is_better",
      threshold: null, adverse_change: 0, regression: false,
    },
  ],
};

interface RunOutcome {
  status: number;
  body: unknown;
}

function stubApi(
  runOutcome: RunOutcome | (() => Promise<RunOutcome>),
  persisted: { runs?: unknown[]; results?: unknown[] } = {},
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "POST" && url.endsWith("/experiments/e1/run")) {
      const outcome =
        typeof runOutcome === "function" ? await runOutcome() : runOutcome;
      return jsonResponse(outcome.body, outcome.status);
    }
    if (url.endsWith("/api/experiments/e1")) return jsonResponse(EXPERIMENT);
    if (url.endsWith("/api/experiments/e1/runs"))
      return jsonResponse(persisted.runs ?? []);
    if (url.endsWith("/api/experiments/e1/results"))
      return jsonResponse(persisted.results ?? []);
    if (url.endsWith("/api/projects/p1/datasets")) return jsonResponse([DATASET]);
    if (url.endsWith("/api/projects/p1/system-versions"))
      return jsonResponse([V1, V2]);
    if (url.endsWith("/api/release-policies")) return jsonResponse([POLICY]);
    throw new Error(`unhandled ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const RUN_RECORD = {
  id: "run-1",
  system_version_id: "v1",
  case_id: "c1",
  repeat_index: 0,
  output: "ok",
  error: null,
  usage: {
    prompt_tokens: 1,
    completion_tokens: 1,
    total_tokens: 2,
    cost_usd: 0,
    latency_ms: 12.3,
  },
  scores: [],
  created_at: "2026-09-08T13:00:00Z",
};

const PERSISTED_PASS = {
  id: "res-persisted",
  experiment_id: "e1",
  created_at: "2026-09-08T13:05:00Z",
  decision: "pass",
  gated: true,
  reasons: [],
  metrics: [
    {
      metric: "contains.pass_rate", baseline_value: 0.9, candidate_value: 1,
      delta: 0.1, relative_delta: 0.111, direction: "higher_is_better",
      threshold: 0.1, adverse_change: -0.111, regression: false,
    },
  ],
};

const PERSISTED_BLOCK = {
  ...PERSISTED_PASS,
  decision: "block",
  reasons: ["contains.pass_rate: higher-is-better regression of 50.0% (limit 10%)"],
  metrics: [
    {
      metric: "contains.pass_rate", baseline_value: 1, candidate_value: 0.5,
      delta: -0.5, relative_delta: -0.5, direction: "higher_is_better",
      threshold: 0.1, adverse_change: 0.5, regression: true,
    },
  ],
};

describe("ExperimentDetailPage", () => {
  it("resolves the configuration to readable labels", async () => {
    stubApi({ status: 201, body: PASS_RESPONSE });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("support v1")).toBeInTheDocument();
    expect(screen.getAllByText(/support-prompt v/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("demo-policy").length).toBeGreaterThan(0);
    // implementation details are not the first thing shown
    expect(screen.queryByText(/None — comparison only/)).not.toBeInTheDocument();
    expect(screen.getByText(/Baseline · current system/i)).toBeInTheDocument();
    expect(screen.getByText(/Candidate · proposed change/i)).toBeInTheDocument();
  });

  it("runs the experiment, disabling the button while pending, then shows PASS", async () => {
    let release: (o: RunOutcome) => void = () => {};
    stubApi(
      () =>
        new Promise<RunOutcome>((resolve) => {
          release = resolve;
        }),
    );

    const user = userEvent.setup();
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    const runButton = await screen.findByRole("button", {
      name: /run evaluation/i,
    });
    await user.click(runButton);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /running/i }),
      ).toBeDisabled(),
    );

    release({ status: 201, body: PASS_RESPONSE });

    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("res-1")).toBeInTheDocument();
    expect(screen.getByText(/1 case · 4 runs/)).toBeInTheDocument();
  });

  it("treats HTTP 201 + BLOCK as a completed run, not an error", async () => {
    stubApi({
      status: 201,
      body: {
        ...PASS_RESPONSE,
        decision: "block",
        reasons: ["latency_ms.p95 regressed by 40% (tolerance 20%)"],
        metrics: [
          {
            metric: "latency_ms.p95", baseline_value: 100, candidate_value: 140,
            delta: 40, relative_delta: 0.4, direction: "lower_is_better",
            threshold: 0.2, adverse_change: 0.4, regression: true,
          },
        ],
      },
    });

    const user = userEvent.setup();
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );

    expect(await screen.findByText("BLOCK")).toBeInTheDocument();
    expect(screen.getByText(/regressed beyond policy/i)).toBeInTheDocument();
    // friendly, human-formatted blocking reason built from backend numbers
    expect(
      screen.getByText("P95 latency regressed 40%; policy allows up to 20%."),
    ).toBeInTheDocument();
    // the backend's verbatim reason string is still available (progressive disclosure)
    expect(
      screen.getByText("latency_ms.p95 regressed by 40% (tolerance 20%)"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/could not be started/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Configuration rejected/i)).not.toBeInTheDocument();
  });

  it("surfaces a 409 duplicate-run response clearly", async () => {
    stubApi({
      status: 409,
      body: { detail: "experiment 'e1' has already been run; its results are immutable" },
    });

    const user = userEvent.setup();
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );

    expect(
      await screen.findByText(/already been run/i),
    ).toBeInTheDocument();
  });

  it("surfaces a 422 configuration error clearly", async () => {
    stubApi({
      status: 422,
      body: { detail: "evaluators[0]: missing required field 'pattern'" },
    });

    const user = userEvent.setup();
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    // switch the single evaluator row to regex_match but leave the pattern set,
    // so the client lets it through and the server rejects it
    await user.selectOptions(
      await screen.findByLabelText("Type"),
      "regex_match",
    );
    await user.type(screen.getByLabelText("Pattern"), "(");
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));

    expect(
      await screen.findByText(/Configuration rejected:/i),
    ).toBeInTheDocument();
  });

  // --- persisted decision (survives refresh; no in-memory run) --------------

  it("shows the persisted PASS decision without a fresh run", async () => {
    stubApi({ status: 201, body: PASS_RESPONSE }, {
      runs: [RUN_RECORD],
      results: [PERSISTED_PASS],
    });

    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(
      screen.getByText(/All gated metrics stayed within the release policy/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/decision recomputed from stored results/i)).toBeInTheDocument();
    // friendly metric name from metric-labels.ts, raw key kept as detail
    expect(screen.getByText("Answer quality")).toBeInTheDocument();
    expect(screen.getByText("contains.pass_rate")).toBeInTheDocument();
    // no run form when a result already exists
    expect(
      screen.queryByRole("button", { name: /run evaluation/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the persisted BLOCK decision with a plain-English reason", async () => {
    stubApi({ status: 201, body: PASS_RESPONSE }, {
      runs: [RUN_RECORD, { ...RUN_RECORD, id: "run-2", system_version_id: "v2" }],
      results: [PERSISTED_BLOCK],
    });

    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("BLOCK")).toBeInTheDocument();
    expect(
      screen.getByText("Answer quality regressed 50%; policy allows up to 10%."),
    ).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument(); // per-metric status
  });
});
