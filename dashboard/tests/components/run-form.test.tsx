import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunForm } from "@/app/projects/[projectId]/experiments/[experimentId]/run-form";
import { jsonResponse, makeWrapper } from "../test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const JOB = {
  id: "job-1",
  experiment_id: "e1",
  status: "queued",
  created_at: "2026-09-10T00:00:00Z",
  started_at: null,
  completed_at: null,
  evaluation_result_id: null,
  error: null,
  celery_task_id: null,
};

function renderForm() {
  const onEnqueued = vi.fn();
  render(<RunForm experimentId="e1" onEnqueued={onEnqueued} />, {
    wrapper: makeWrapper(),
  });
  return { onEnqueued };
}

describe("RunForm — RAG & agent evaluator configuration", () => {
  it("offers RAG and agent evaluator types grouped by family", () => {
    renderForm();
    const select = screen.getByLabelText("Type");
    for (const type of [
      "retrieval_recall",
      "context_precision",
      "groundedness",
      "tool_selection",
      "tool_arguments",
      "tool_success",
      "tool_trajectory",
    ]) {
      expect(
        screen.getByRole("option", { name: type }),
      ).toBeInTheDocument();
    }
    expect(select).toBeInTheDocument();
  });

  it("shows the RAG threshold, the label requirement, and RAG product copy", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.selectOptions(screen.getByLabelText("Type"), "retrieval_recall");

    expect(
      screen.getByLabelText(/min_recall \(pass threshold/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Needs expected_retrieval_ids on every case/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/evaluate what the system retrieved as well as what it answered/i),
    ).toBeInTheDocument();
  });

  it("shows the agent threshold, label requirement, and agent product copy", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.selectOptions(screen.getByLabelText("Type"), "tool_arguments");

    expect(
      screen.getByLabelText(/min_score \(pass threshold/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Needs expected_tool_calls with explicit arguments/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/tool selection, arguments, execution success, and trajectory/i),
    ).toBeInTheDocument();
  });

  it("sends only the supported threshold key in the run request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(JOB, 202));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { onEnqueued } = renderForm();

    await user.selectOptions(screen.getByLabelText("Type"), "tool_selection");
    const threshold = screen.getByLabelText(/min_score \(pass threshold/);
    await user.clear(threshold);
    await user.type(threshold, "0.5");
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));

    await waitFor(() => expect(onEnqueued).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/experiments/e1/run-async");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      execution: { backend: "mock" },
      evaluators: [{ type: "tool_selection", min_score: 0.5 }],
    });
  });

  it("blocks an out-of-range threshold client-side but keeps the backend authoritative", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.selectOptions(screen.getByLabelText("Type"), "groundedness");
    const threshold = screen.getByLabelText(/min_groundedness \(pass threshold/);
    await user.clear(threshold);
    await user.type(threshold, "5");

    expect(screen.getByText(/must be a number between 0 and 1/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /run evaluation/i }),
    ).toBeDisabled();
    expect(
      screen.getByText(/backend validates labels and rejects a mismatch/i),
    ).toBeInTheDocument();
  });

  it("surfaces a backend 422 (label mismatch) without recomputing anything", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { detail: "retrieval_recall requires expected_retrieval_ids" },
            422,
          ),
        ),
    );
    const user = userEvent.setup();
    renderForm();
    await user.selectOptions(screen.getByLabelText("Type"), "tool_success");
    await user.click(screen.getByRole("button", { name: /run evaluation/i }));

    expect(
      await screen.findByText(/Configuration rejected:/),
    ).toBeInTheDocument();
  });
});
