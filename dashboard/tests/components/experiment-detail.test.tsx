import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExperimentDetailPage from "@/app/projects/[projectId]/experiments/[experimentId]/page";
import type { AsyncJobStatus } from "@/lib/api/types";
import { JOB_POLL_INTERVAL_MS } from "@/lib/query/experiments";
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

beforeEach(() => {
  // React Query's poll interval drives the whole async flow; fake timers keep
  // the queued -> running -> completed progression fast and deterministic.
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
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

const EVIDENCE_PASS = {
  metric: "contains.pass_rate", kind: "binary", n_pairs: 8,
  baseline: { n: 8, mean: 0.9, median: 0.9, stdev: 0.1 },
  candidate: { n: 8, mean: 1, median: 1, stdev: 0 },
  paired_delta: { n: 8, mean: 0.1, median: 0.1, stdev: 0.1 },
  delta: 0.1, relative_change: 0.111, confidence_level: 0.95,
  ci_low: 0.02, ci_high: 0.2, ci_excludes_zero: true,
  insufficient_evidence: false, dropped_provider_failures: 0,
  method: "paired_bootstrap_percentile",
};

const PERSISTED_PASS = {
  id: "res-persisted",
  experiment_id: "e1",
  created_at: "2026-09-08T13:05:00Z",
  decision: "pass",
  gated: true,
  reasons: [],
  advisories: [],
  evidence: [EVIDENCE_PASS],
  metrics: [
    {
      metric: "contains.pass_rate", baseline_value: 0.9, candidate_value: 1,
      delta: 0.1, relative_delta: 0.111, direction: "higher_is_better",
      threshold: 0.1, adverse_change: -0.111, regression: false, gate_outcome: "pass",
    },
  ],
};

const PERSISTED_BLOCK = {
  ...PERSISTED_PASS,
  decision: "block",
  reasons: ["contains.pass_rate: higher-is-better regression of 50.0% (limit 10%)"],
  advisories: [],
  evidence: [
    {
      ...EVIDENCE_PASS,
      candidate: { n: 8, mean: 0.5, median: 0.5, stdev: 0.1 },
      paired_delta: { n: 8, mean: -0.5, median: -0.5, stdev: 0.1 },
      delta: -0.5, relative_change: -0.5, ci_low: -0.6, ci_high: -0.4,
    },
  ],
  metrics: [
    {
      metric: "contains.pass_rate", baseline_value: 1, candidate_value: 0.5,
      delta: -0.5, relative_delta: -0.5, direction: "higher_is_better",
      threshold: 0.1, adverse_change: 0.5, regression: true, gate_outcome: "regression",
    },
  ],
};

const PERSISTED_PASS_WITH_ADVISORY = {
  ...PERSISTED_PASS,
  advisories: [
    "contains.pass_rate: observed higher-is-better regression of 30.0% exceeds the 10% limit, but only 3 paired sample(s) (minimum 8) -- insufficient evidence to block; increase repeats or dataset size",
  ],
  evidence: [
    {
      ...EVIDENCE_PASS,
      n_pairs: 3,
      baseline: { n: 3, mean: 1, median: 1, stdev: 0 },
      candidate: { n: 3, mean: 0.7, median: 0.7, stdev: 0.1 },
      paired_delta: { n: 3, mean: -0.3, median: -0.3, stdev: 0.1 },
      delta: -0.3, relative_change: -0.3,
      ci_low: null, ci_high: null, ci_excludes_zero: false,
      insufficient_evidence: true,
    },
  ],
  metrics: [
    {
      metric: "contains.pass_rate", baseline_value: 1, candidate_value: 0.7,
      delta: -0.3, relative_delta: -0.3, direction: "higher_is_better",
      threshold: 0.1, adverse_change: 0.3, regression: false,
      gate_outcome: "regression_low_evidence",
    },
  ],
};

/** An `async_job` row shape, keyed off the lifecycle status. */
function makeJob(
  status: AsyncJobStatus,
  overrides: Record<string, unknown> = {},
) {
  const terminal = status === "completed" || status === "failed";
  return {
    id: "job-1",
    experiment_id: "e1",
    status,
    created_at: "2026-09-08T13:00:00Z",
    started_at: status === "queued" ? null : "2026-09-08T13:00:01Z",
    completed_at: terminal ? "2026-09-08T13:00:05Z" : null,
    evaluation_result_id: status === "completed" ? "res-persisted" : null,
    error:
      status === "failed"
        ? "regex_match evaluator: bad pattern '(' — missing ), unterminated subpattern"
        : null,
    celery_task_id: status === "queued" ? null : "task-abc",
    ...overrides,
  };
}

interface StubOptions {
  /** Response for POST /experiments/e1/run-async. Default: 202 + queued job. */
  enqueue?: { status: number; body?: unknown };
  /** Sequential GET /jobs/{id} statuses; the last one repeats. */
  stages?: AsyncJobStatus[];
  /** Block the enqueue response until this resolves (to observe the pending UI). */
  holdEnqueue?: Promise<unknown>;
  runs?: unknown[];
  results?: unknown[];
  /** Results returned once a terminal job has been polled (simulates persistence). */
  resultsWhenDone?: unknown[];
}

function stubApi(opts: StubOptions = {}) {
  const {
    enqueue = { status: 202, body: makeJob("queued") },
    stages = ["queued", "running", "completed"],
    holdEnqueue,
    runs = [],
    results = [],
    resultsWhenDone,
  } = opts;

  let jobPolls = 0;
  let reachedTerminal = false;

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();

    if (method === "POST" && url.endsWith("/experiments/e1/run-async")) {
      if (holdEnqueue) await holdEnqueue;
      return jsonResponse(enqueue.body ?? makeJob("queued"), enqueue.status);
    }
    if (method === "GET" && url.includes("/api/jobs/")) {
      const stage =
        stages[Math.min(jobPolls, stages.length - 1)] ?? "completed";
      jobPolls += 1;
      if (stage === "completed" || stage === "failed") reachedTerminal = true;
      return jsonResponse(makeJob(stage), 200);
    }
    if (url.endsWith("/api/experiments/e1")) return jsonResponse(EXPERIMENT);
    if (url.endsWith("/api/experiments/e1/runs")) return jsonResponse(runs);
    if (url.endsWith("/api/experiments/e1/results")) {
      return jsonResponse(
        reachedTerminal && resultsWhenDone ? resultsWhenDone : results,
      );
    }
    if (url.endsWith("/api/projects/p1/datasets")) return jsonResponse([DATASET]);
    if (url.endsWith("/api/projects/p1/system-versions"))
      return jsonResponse([V1, V2]);
    if (url.endsWith("/api/release-policies")) return jsonResponse([POLICY]);
    throw new Error(`unhandled ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  const countCalls = (predicate: (url: string, init?: RequestInit) => boolean) =>
    fetchMock.mock.calls.filter(([u, i]) =>
      predicate(String(u), i as RequestInit | undefined),
    ).length;

  return {
    fetchMock,
    jobPollCount: () =>
      countCalls(
        (u, i) =>
          (i?.method ?? "GET").toUpperCase() === "GET" && u.includes("/api/jobs/"),
      ),
    enqueueCount: () =>
      countCalls(
        (u, i) =>
          (i?.method ?? "GET").toUpperCase() === "POST" &&
          u.endsWith("/experiments/e1/run-async"),
      ),
  };
}

describe("ExperimentDetailPage", () => {
  it("resolves the configuration to readable labels", async () => {
    stubApi();
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("support v1")).toBeInTheDocument();
    expect(screen.getAllByText(/support-prompt v/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("demo-policy").length).toBeGreaterThan(0);
    expect(screen.getByText(/Baseline · current system/i)).toBeInTheDocument();
    expect(screen.getByText(/Candidate · proposed change/i)).toBeInTheDocument();
  });

  it("queues a background run and locks out a second submit while it is active", async () => {
    let release: () => void = () => {};
    const hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { fetchMock, enqueueCount } = stubApi({ holdEnqueue: hold });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    const runButton = await screen.findByRole("button", {
      name: /run evaluation/i,
    });
    await user.click(runButton);

    // enqueue POST in flight: the button is relabelled and disabled
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /queuing/i })).toBeDisabled(),
    );

    release();

    // 202 lands -> the form is replaced by the lifecycle panel; no Run button
    expect(await screen.findByText(/^Queued$/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /run evaluation/i }),
    ).not.toBeInTheDocument();

    // the async endpoint is hit once; the sync /run endpoint is never used
    expect(enqueueCount()).toBe(1);
    expect(
      fetchMock.mock.calls.some(([u, i]) => {
        const url = String(u);
        return (
          ((i as RequestInit | undefined)?.method ?? "GET").toUpperCase() ===
            "POST" && url.endsWith("/experiments/e1/run") // exact sync path
        );
      }),
    ).toBe(false);
  });

  it("polls queued -> running -> completed, then shows the persisted PASS decision", async () => {
    const { jobPollCount } = stubApi({
      stages: ["queued", "running", "completed"],
      resultsWhenDone: [PERSISTED_PASS],
    });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );

    expect(await screen.findByText(/^Queued$/)).toBeInTheDocument();
    expect(jobPollCount()).toBe(1);

    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);
    expect(await screen.findByText(/^Running$/)).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);
    expect(await screen.findByText(/^Completed$/)).toBeInTheDocument();

    // the persisted decision was refreshed through the existing results API
    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getAllByText("Answer quality").length).toBeGreaterThan(0);

    // polling has stopped now that the job is terminal
    const atTerminal = jobPollCount();
    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS * 5);
    expect(jobPollCount()).toBe(atTerminal);
  });

  it("renders a completed BLOCK as a release decision, not a run failure", async () => {
    stubApi({
      stages: ["queued", "completed"],
      resultsWhenDone: [PERSISTED_BLOCK],
    });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );
    await screen.findByText(/^Queued$/);
    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);

    expect(await screen.findByText("BLOCK")).toBeInTheDocument();
    expect(
      screen.getByText("Answer quality regressed 50%; policy allows up to 10%."),
    ).toBeInTheDocument();
    // it is a completed run, not a worker failure
    expect(screen.getByText(/^Completed$/)).toBeInTheDocument();
    expect(screen.queryByText(/failed on the worker/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /try running again/i }),
    ).not.toBeInTheDocument();
  });

  it("shows a failed job with its persisted error and offers a retry", async () => {
    stubApi({ stages: ["queued", "running", "failed"] });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );
    await screen.findByText(/^Queued$/);
    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);
    await vi.advanceTimersByTimeAsync(JOB_POLL_INTERVAL_MS);

    expect(await screen.findByText(/^Failed$/)).toBeInTheDocument();
    // the persisted job error is surfaced verbatim
    expect(screen.getByText(/unterminated subpattern/i)).toBeInTheDocument();
    expect(screen.queryByText("PASS")).not.toBeInTheDocument();
    expect(screen.queryByText("BLOCK")).not.toBeInTheDocument();

    // retry clears the job and returns to the run form
    await user.click(screen.getByRole("button", { name: /try running again/i }));
    expect(
      await screen.findByRole("button", { name: /run evaluation/i }),
    ).toBeInTheDocument();
  });

  it("surfaces an enqueue (broker) failure on the form, not as a worker failure", async () => {
    const { jobPollCount } = stubApi({
      enqueue: {
        status: 500,
        body: {
          detail:
            "the run for experiment 'e1' could not be dispatched to the task broker; job 'abc' was marked failed",
        },
      },
    });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    await user.click(
      await screen.findByRole("button", { name: /run evaluation/i }),
    );

    expect(
      await screen.findByText(/task broker is unavailable/i),
    ).toBeInTheDocument();
    // nothing was queued, so nothing is polled; the form stays available to retry
    expect(jobPollCount()).toBe(0);
    expect(
      screen.getByRole("button", { name: /run evaluation/i }),
    ).toBeEnabled();
  });

  it("surfaces a 422 configuration error from the async endpoint", async () => {
    stubApi({
      enqueue: {
        status: 422,
        body: { detail: "evaluators[0]: missing required field 'pattern'" },
      },
    });

    const user = userEvent.setup({ delay: null });
    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

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

  // --- persisted decision (survives refresh; no in-memory job) --------------

  it("shows the persisted PASS decision without a fresh run", async () => {
    stubApi({ runs: [RUN_RECORD], results: [PERSISTED_PASS] });

    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(
      screen.getByText(/All gated metrics stayed within the release policy/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/decision recomputed from stored results/i),
    ).toBeInTheDocument();
    // friendly + raw metric name appear in the table (and again in the evidence row)
    expect(screen.getAllByText("Answer quality").length).toBeGreaterThan(0);
    expect(screen.getAllByText("contains.pass_rate").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: /run evaluation/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the persisted BLOCK decision with a plain-English reason and evidence", async () => {
    stubApi({
      runs: [RUN_RECORD, { ...RUN_RECORD, id: "run-2", system_version_id: "v2" }],
      results: [PERSISTED_BLOCK],
    });

    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("BLOCK")).toBeInTheDocument();
    expect(
      screen.getByText("Answer quality regressed 50%; policy allows up to 10%."),
    ).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    // CP 5.3: persisted evidence renders on the recomputed-from-storage path
    expect(screen.getByText(/Statistical evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/8 paired samples/)).toBeInTheDocument();
    expect(screen.getByText("CI supports a regression")).toBeInTheDocument();
  });

  it("shows a persisted PASS-with-advisory as not an unconditional safe pass", async () => {
    stubApi({
      runs: [RUN_RECORD],
      results: [PERSISTED_PASS_WITH_ADVISORY],
    });

    render(<ExperimentDetailPage />, { wrapper: makeWrapper() });

    expect(await screen.findByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/with unverified concerns/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Do not read this as an unconditional pass/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/insufficient evidence to block/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Breach — low evidence")).toBeInTheDocument();
    expect(screen.getByText(/95% CI not computed/)).toBeInTheDocument();
    // still the persisted path — survives without a fresh run
    expect(
      screen.getByText(/decision recomputed from stored results/i),
    ).toBeInTheDocument();
  });
});
