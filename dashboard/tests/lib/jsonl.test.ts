import { describe, expect, it } from "vitest";
import { parseCasesJsonl } from "@/lib/jsonl";

describe("parseCasesJsonl", () => {
  it("returns nothing for empty input", () => {
    expect(parseCasesJsonl("")).toEqual({ cases: [], errors: [] });
  });

  it("skips blank and whitespace-only lines", () => {
    const result = parseCasesJsonl('\n  \n{"input": "a"}\n\n');
    expect(result.errors).toEqual([]);
    expect(result.cases).toEqual([{ input: "a" }]);
  });

  it("parses multiple cases with optional fields", () => {
    const text = [
      '{"input": "q1", "expected_output": "a1"}',
      '{"input": "q2", "origin": "promoted_trace", "source_trace_id": "t-9"}',
    ].join("\n");
    const result = parseCasesJsonl(text);
    expect(result.errors).toEqual([]);
    expect(result.cases).toEqual([
      { input: "q1", expected_output: "a1" },
      { input: "q2", origin: "promoted_trace", source_trace_id: "t-9" },
    ]);
  });

  it("reports invalid JSON with a 1-based line number", () => {
    const result = parseCasesJsonl('{"input": "ok"}\nnot json');
    expect(result.cases).toEqual([{ input: "ok" }]);
    expect(result.errors).toEqual([{ line: 2, message: "not valid JSON" }]);
  });

  it("rejects a non-object line", () => {
    const result = parseCasesJsonl('["a", "b"]');
    expect(result.cases).toEqual([]);
    expect(result.errors[0]).toMatchObject({ line: 1 });
  });

  it("requires a non-empty string input", () => {
    expect(parseCasesJsonl('{"expected_output": "a"}').errors[0]?.message).toContain(
      '"input"',
    );
    expect(parseCasesJsonl('{"input": "   "}').errors).toHaveLength(1);
  });

  it("rejects a non-string expected_output and a bad origin", () => {
    expect(parseCasesJsonl('{"input": "a", "expected_output": 3}').errors).toHaveLength(
      1,
    );
    expect(parseCasesJsonl('{"input": "a", "origin": "guess"}').errors).toHaveLength(
      1,
    );
  });

  it("parses RAG expected_retrieval_ids", () => {
    const r = parseCasesJsonl(
      '{"input": "q", "expected_retrieval_ids": ["kb-1", "kb-2"]}',
    );
    expect(r.errors).toEqual([]);
    expect(r.cases).toEqual([
      { input: "q", expected_retrieval_ids: ["kb-1", "kb-2"] },
    ]);
  });

  it("rejects a non-string-list expected_retrieval_ids", () => {
    expect(
      parseCasesJsonl('{"input": "q", "expected_retrieval_ids": [1, 2]}').errors,
    ).toHaveLength(1);
    expect(
      parseCasesJsonl('{"input": "q", "expected_retrieval_ids": "kb-1"}').errors,
    ).toHaveLength(1);
  });

  it("parses agent expected_tool_calls with name-only and argument-labelled entries", () => {
    const r = parseCasesJsonl(
      '{"input": "q", "expected_tool_calls": [{"name": "search", "arguments": {"q": "x"}}, {"name": "done"}]}',
    );
    expect(r.errors).toEqual([]);
    expect(r.cases[0]?.expected_tool_calls).toEqual([
      { name: "search", arguments: { q: "x" } },
      { name: "done" },
    ]);
  });

  it("rejects malformed expected_tool_calls", () => {
    expect(
      parseCasesJsonl('{"input": "q", "expected_tool_calls": [{"arguments": {}}]}')
        .errors,
    ).toHaveLength(1); // missing name
    expect(
      parseCasesJsonl(
        '{"input": "q", "expected_tool_calls": [{"name": "t", "arguments": [1]}]}',
      ).errors,
    ).toHaveLength(1); // arguments not an object
    expect(
      parseCasesJsonl('{"input": "q", "expected_tool_calls": "search"}').errors,
    ).toHaveLength(1);
  });
});
