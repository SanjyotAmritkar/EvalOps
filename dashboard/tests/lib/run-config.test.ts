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

const row = (over: Partial<RunConfigState["evaluators"][number]> = {}) => ({
  type: "contains" as const,
  name: "",
  caseSensitive: false,
  pattern: "",
  threshold: "",
  ...over,
});

describe("buildRunRequest", () => {
  it("serializes a mock run with only the fields each evaluator type supports", () => {
    const state = base({
      evaluators: [
        row({ type: "contains", caseSensitive: false }),
        row({ type: "exact_match", name: "strict", caseSensitive: true }),
        row({ type: "regex_match", caseSensitive: true, pattern: "^yes" }),
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

  it("serializes RAG and agent evaluators with only their supported threshold key", () => {
    const state = base({
      evaluators: [
        row({ type: "retrieval_recall", threshold: "0.8" }),
        row({ type: "context_precision", threshold: "" }), // blank -> backend default
        row({ type: "groundedness", threshold: "0.6" }),
        row({ type: "tool_selection", threshold: "0.5" }),
        row({ type: "tool_arguments", threshold: "" }),
        row({ type: "tool_success", name: "calls_ok", threshold: "1" }),
        row({ type: "tool_trajectory", threshold: "0.9" }),
      ],
    });

    expect(buildRunRequest(state).evaluators).toEqual([
      { type: "retrieval_recall", min_recall: 0.8 },
      { type: "context_precision" },
      { type: "groundedness", min_groundedness: 0.6 },
      { type: "tool_selection", min_score: 0.5 },
      { type: "tool_arguments" },
      { type: "tool_success", name: "calls_ok", min_score: 1 },
      { type: "tool_trajectory", min_score: 0.9 },
    ]);
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
      base({ evaluators: [row({ type: "regex_match", caseSensitive: true, pattern: "  " })] }),
    );
    expect(errors.rows[0]).toMatch(/pattern/i);
    expect(isRunConfigValid(errors)).toBe(false);
  });

  it("rejects an out-of-range evaluator threshold", () => {
    const errors = validateRunConfig(
      base({ evaluators: [row({ type: "retrieval_recall", threshold: "1.5" })] }),
    );
    expect(errors.rows[0]).toMatch(/between 0 and 1/i);
    expect(isRunConfigValid(errors)).toBe(false);
    // blank threshold is accepted (backend default)
    expect(
      isRunConfigValid(
        validateRunConfig(base({ evaluators: [row({ type: "retrieval_recall", threshold: "" })] })),
      ),
    ).toBe(true);
  });

  it("rejects duplicate effective evaluator names", () => {
    const errors = validateRunConfig(
      base({
        evaluators: [
          row({ type: "contains", caseSensitive: false }),
          row({ type: "contains", name: "contains", caseSensitive: false }),
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
