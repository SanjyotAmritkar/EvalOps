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
});
