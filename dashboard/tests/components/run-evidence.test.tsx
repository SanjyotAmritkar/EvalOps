import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RunEvidence } from "@/app/projects/[projectId]/experiments/[experimentId]/run-evidence";
import type { EvaluationRun } from "@/lib/api/types";

function run(overrides: Partial<EvaluationRun> = {}): EvaluationRun {
  return {
    id: "r1",
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
      latency_ms: 5,
    },
    scores: [
      { evaluator: "retrieval_recall", family: "statistical", score: 0.5, passed: false },
    ],
    retrieval: [],
    tool_calls: [],
    created_at: "2026-09-10T00:00:00Z",
    ...overrides,
  };
}

describe("RunEvidence", () => {
  it("a text-only run shows scores but no RAG or agent sections", () => {
    render(<RunEvidence run={run({ scores: [] })} />);
    expect(screen.getByText("Evaluator scores")).toBeInTheDocument();
    expect(screen.queryByText("Retrieved context")).not.toBeInTheDocument();
    expect(screen.queryByText("Tool trajectory")).not.toBeInTheDocument();
  });

  it("empty retrieval array renders no Retrieved context section", () => {
    render(<RunEvidence run={run({ retrieval: [] })} />);
    expect(screen.queryByText("Retrieved context")).not.toBeInTheDocument();
  });

  it("renders retrieved context with rank, id, score and content, labelled as not ground truth", () => {
    render(
      <RunEvidence
        run={run({
          retrieval: [
            { doc_id: "kb-2", content: "second chunk", rank: 1, score: 0.4 },
            { doc_id: "kb-1", content: "first chunk", rank: 0, score: null },
          ],
        })}
      />,
    );
    const section = screen.getByText("Retrieved context").closest("section")!;
    expect(section).toHaveTextContent("not evaluation ground truth");
    expect(within(section).getByText("kb-2")).toBeInTheDocument();
    expect(within(section).getByText("#1")).toBeInTheDocument();
    expect(within(section).getByText(/score 0\.400/)).toBeInTheDocument();
    expect(within(section).getByText("first chunk")).toBeInTheDocument();
  });

  it("renders the tool trajectory in order with arguments, result and error", () => {
    render(
      <RunEvidence
        run={run({
          tool_calls: [
            { name: "search", arguments: { q: "cats" }, result: { hits: 3 }, ok: true, error: null },
            { name: "delete", arguments: {}, result: null, ok: false, error: "denied" },
          ],
        })}
      />,
    );
    const section = screen.getByText("Tool trajectory").closest("section")!;
    expect(section).toHaveTextContent("does not by itself prove the task was solved correctly");

    const items = within(section).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("1.");
    expect(items[0]).toHaveTextContent("search");
    expect(items[0]).toHaveTextContent("ok");
    expect(items[0]).toHaveTextContent('"q": "cats"');
    expect(items[0]).toHaveTextContent('"hits": 3');
    expect(items[1]).toHaveTextContent("2.");
    expect(items[1]).toHaveTextContent("delete");
    expect(items[1]).toHaveTextContent("failed");
    expect(items[1]).toHaveTextContent("denied");
  });
});
