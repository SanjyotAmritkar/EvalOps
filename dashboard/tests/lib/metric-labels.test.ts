import { describe, expect, it } from "vitest";
import {
  metricKind,
  metricKindLabel,
  metricLabel,
} from "@/lib/metric-labels";

describe("metricLabel — RAG & agent metrics", () => {
  it("gives human-readable names for every RAG metric", () => {
    expect(metricLabel("retrieval_recall.pass_rate")).toBe(
      "Retrieval recall — pass rate",
    );
    expect(metricLabel("retrieval_recall.mean_score")).toBe(
      "Retrieval recall — mean score",
    );
    expect(metricLabel("context_precision.pass_rate")).toBe(
      "Context precision — pass rate",
    );
    expect(metricLabel("context_precision.mean_score")).toBe(
      "Context precision — mean score",
    );
    expect(metricLabel("groundedness_lexical.pass_rate")).toBe(
      "Answer groundedness (lexical) — pass rate",
    );
    expect(metricLabel("groundedness_lexical.mean_score")).toBe(
      "Answer groundedness (lexical) — mean score",
    );
  });

  it("gives human-readable names for every agent metric", () => {
    for (const base of [
      "tool_selection",
      "tool_arguments",
      "tool_success",
      "tool_trajectory",
    ]) {
      expect(metricLabel(`${base}.pass_rate`)).toMatch(/ — pass rate$/);
      expect(metricLabel(`${base}.mean_score`)).toMatch(/ — mean score$/);
    }
    expect(metricLabel("tool_trajectory.mean_score")).toBe(
      "Tool trajectory — mean score",
    );
  });

  it("keeps the classic short labels", () => {
    expect(metricLabel("success_rate")).toBe("Reliability");
    expect(metricLabel("contains.pass_rate")).toBe("Answer quality");
    expect(metricLabel("latency_ms.p95")).toBe("P95 latency");
  });

  it("falls back for an unknown custom evaluator name", () => {
    expect(metricLabel("my_eval.pass_rate")).toBe("my_eval pass rate");
    expect(metricLabel("my_eval.mean_score")).toBe("my_eval mean score");
  });

  it("classifies pass_rate vs mean_score", () => {
    expect(metricKind("tool_selection.pass_rate")).toBe("pass_rate");
    expect(metricKind("tool_selection.mean_score")).toBe("mean_score");
    expect(metricKind("latency_ms.p95")).toBeNull();
    expect(metricKindLabel("retrieval_recall.mean_score")).toBe("mean score");
    expect(metricKindLabel("retrieval_recall.pass_rate")).toBe("pass rate");
    expect(metricKindLabel("cost_usd.total")).toBeNull();
  });
});
