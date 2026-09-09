import { describe, expect, it } from "vitest";
import {
  buildRunRequest,
  isRunConfigValid,
  newEvaluatorRow,
  validateRunConfig,
  type RunConfigState,
} from "@/lib/run-config";

function base(overrides: Partial<RunConfigState> = {}): RunConfigState {
  return {
    backend: "mock",
    baseUrl: "http://localhost:11434",
    timeoutSeconds: "120",
    evaluators: [newEvaluatorRow("contains")],
    ...overrides,
  };
}

describe("buildRunRequest", () => {
  it("serializes a mock run with only the fields each evaluator type supports", () => {
    const state = base({
      evaluators: [
        { type: "contains", name: "", caseSensitive: false, pattern: "" },
        { type: "exact_match", name: "strict", caseSensitive: true, pattern: "" },
        { type: "regex_match", name: "", caseSensitive: true, pattern: "^yes" },
      ],
    });

    expect(buildRunRequest(state)).toEqual({
      execution: { backend: "mock" },
      evaluators: [
        { type: "contains", case_sensitive: false },
        { type: "exact_match", name: "strict", case_sensitive: true },
        { type: "regex_match", pattern: "^yes" },
      ],
    });
  });

  it("includes base_url and a numeric timeout for the ollama backend", () => {
    const request = buildRunRequest(
      base({ backend: "ollama", baseUrl: "http://host:1234 ", timeoutSeconds: "90" }),
    );
    expect(request.execution).toEqual({
      backend: "ollama",
      base_url: "http://host:1234",
      timeout_seconds: 90,
    });
    expect(typeof request.execution.timeout_seconds).toBe("number");
  });
});

describe("validateRunConfig", () => {
  it("accepts a minimal valid config", () => {
    expect(isRunConfigValid(validateRunConfig(base()))).toBe(true);
  });

  it("requires a pattern for regex_match rows", () => {
    const errors = validateRunConfig(
      base({
        evaluators: [{ type: "regex_match", name: "", caseSensitive: true, pattern: "  " }],
      }),
    );
    expect(errors.rows[0]).toMatch(/pattern/i);
    expect(isRunConfigValid(errors)).toBe(false);
  });

  it("rejects duplicate effective evaluator names", () => {
    const errors = validateRunConfig(
      base({
        evaluators: [
          { type: "contains", name: "", caseSensitive: false, pattern: "" },
          { type: "contains", name: "contains", caseSensitive: false, pattern: "" },
        ],
      }),
    );
    expect(errors.evaluators).toMatch(/unique/i);
  });

  it("rejects an empty evaluator list", () => {
    expect(validateRunConfig(base({ evaluators: [] })).evaluators).toMatch(/at least one/i);
  });

  it("validates ollama base url and timeout", () => {
    expect(
      validateRunConfig(base({ backend: "ollama", timeoutSeconds: "0" })).ollama,
    ).toMatch(/timeout/i);
    expect(
      validateRunConfig(base({ backend: "ollama", baseUrl: "  " })).ollama,
    ).toMatch(/base url/i);
    expect(
      validateRunConfig(base({ backend: "ollama", timeoutSeconds: "30" })).ollama,
    ).toBeNull();
  });
});
