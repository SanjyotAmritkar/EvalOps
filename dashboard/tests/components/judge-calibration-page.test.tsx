import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import JudgeCalibrationsPage from "@/app/projects/[projectId]/judge-calibrations/page";
import type { JudgeCalibration } from "@/lib/api/types";
import { jsonResponse, makeWrapper } from "../test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const PERSISTED: JudgeCalibration = {
  id: "cal-9",
  created_at: "2026-09-09T10:00:00Z",
  judge_provider: "openai",
  judge_model: "gpt-4o-mini",
  judge_name: "correctness",
  judge_temperature: 0,
  rubric_id: "judge-v1",
  metrics: {
    total: 3,
    scored: 3,
    failures: 0,
    agreements: 2,
    agreement_rate: 2 / 3,
    true_positives: 1,
    true_negatives: 1,
    false_positives: 1,
    false_negatives: 0,
    precision: 0.5,
    recall: 1,
    f1: 2 / 3,
  },
  cases: [
    {
      input: "2+2?",
      output: "4",
      reference: "4",
      human_pass: true,
      judge_pass: true,
      judge_score: 0.9,
      judge_reasoning: "correct",
      error: null,
    },
    {
      input: "capital of France?",
      output: "Berlin",
      reference: "Paris",
      human_pass: false,
      judge_pass: false,
      judge_score: 0.1,
      judge_reasoning: "wrong city",
      error: null,
    },
    {
      input: "sky colour?",
      output: "blue-ish",
      reference: "blue",
      human_pass: false,
      judge_pass: true,
      judge_score: 0.6,
      judge_reasoning: "close enough",
      error: null,
    },
  ],
};

function stubApi(opts: {
  list?: JudgeCalibration[];
  created?: JudgeCalibration;
  detail?: JudgeCalibration;
}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "POST" && url.endsWith("/api/judge-calibrations")) {
      return jsonResponse(opts.created, 201);
    }
    if (url.endsWith("/api/judge-calibrations")) {
      return jsonResponse(opts.list ?? []);
    }
    if (url.includes("/api/judge-calibrations/")) {
      return jsonResponse(opts.detail ?? opts.created ?? PERSISTED);
    }
    throw new Error(`unhandled ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("JudgeCalibrationsPage", () => {
  it("explains that calibration does not affect release gating", async () => {
    stubApi({ list: [] });
    render(<JudgeCalibrationsPage />, { wrapper: makeWrapper() });

    expect(
      await screen.findByText(/does not affect release gating/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/measures judge trustworthiness only/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/read from the server environment/i)).toBeInTheDocument();
    expect(await screen.findByText("No calibrations yet")).toBeInTheDocument();
  });

  it("retrieves a persisted calibration from the list and renders its metrics", async () => {
    const fetchMock = stubApi({ list: [PERSISTED], detail: PERSISTED });
    const user = userEvent.setup();
    render(<JudgeCalibrationsPage />, { wrapper: makeWrapper() });

    // summary row from the list
    const row = await screen.findByRole("button", { name: /correctness/i });
    await user.click(row);

    // full result rendered from GET /judge-calibrations/{id}
    expect(await screen.findByText("Calibration result")).toBeInTheDocument();
    expect(
      screen.getByText(/Per-example: human verdict vs judge verdict/i),
    ).toBeInTheDocument();
    expect(screen.getByText("wrong city")).toBeInTheDocument();
    expect(screen.getByText("close enough")).toBeInTheDocument();
    expect(screen.getByText("← Back to all calibrations")).toBeInTheDocument();

    // the detail endpoint was actually hit
    expect(
      fetchMock.mock.calls.some(([u]) =>
        String(u).includes("/api/judge-calibrations/cal-9"),
      ),
    ).toBe(true);
  });

  it("runs a calibration from the form and shows the result", async () => {
    const created: JudgeCalibration = { ...PERSISTED, id: "cal-new" };
    const fetchMock = stubApi({ list: [], created, detail: created });
    const user = userEvent.setup();
    render(<JudgeCalibrationsPage />, { wrapper: makeWrapper() });

    await screen.findByText("No calibrations yet");
    await user.click(
      screen.getAllByRole("button", { name: /new calibration/i })[0]!,
    );

    await user.type(screen.getByLabelText("Judge model"), "gpt-4o-mini");
    await user.type(screen.getByLabelText("Example 1 input"), "2+2?");
    await user.type(screen.getByLabelText("Example 1 system output"), "4");
    await user.type(
      screen.getByLabelText("Example 2 input"),
      "capital of France?",
    );
    await user.type(
      screen.getByLabelText("Example 2 system output"),
      "Berlin",
    );
    await user.selectOptions(
      screen.getByLabelText("Example 2 human verdict"),
      "fail",
    );
    await user.type(screen.getByLabelText("Example 3 input"), "sky?");
    await user.type(screen.getByLabelText("Example 3 system output"), "blue");

    const submit = screen.getByRole("button", { name: /run calibration/i });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    expect(await screen.findByText("Calibration result")).toBeInTheDocument();

    const post = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/judge-calibrations");
    const body = JSON.parse((post?.[1] as RequestInit).body as string);
    expect(body.provider).toBe("openai");
    expect(body.model).toBe("gpt-4o-mini");
    expect(body.temperature).toBe(0);
    expect(body.examples).toHaveLength(3);
    expect(body.examples[0]).toEqual({
      input: "2+2?",
      output: "4",
      human_pass: true,
    });
    expect(body.examples[1].human_pass).toBe(false);
    // no api key / credential field is ever sent
    expect(JSON.stringify(body)).not.toMatch(/api[_-]?key/i);
  });
});
