import { describe, expect, it } from "vitest";
import { formatJson, parseJsonObject } from "@/lib/json";

describe("parseJsonObject", () => {
  it("treats blank input as an absent value, not an error", () => {
    expect(parseJsonObject("   ")).toEqual({ value: null, error: null });
  });

  it("parses a JSON object", () => {
    expect(parseJsonObject('{"temperature": 0}')).toEqual({
      value: { temperature: 0 },
      error: null,
    });
  });

  it("flags invalid JSON", () => {
    expect(parseJsonObject("{bad").error).toBe("not valid JSON");
  });

  it("rejects arrays and primitives", () => {
    expect(parseJsonObject("[1, 2]").error).toBe("must be a JSON object");
    expect(parseJsonObject("42").error).toBe("must be a JSON object");
  });
});

describe("formatJson", () => {
  it("pretty-prints with two-space indentation", () => {
    expect(formatJson({ a: 1 })).toBe('{\n  "a": 1\n}');
  });
});
