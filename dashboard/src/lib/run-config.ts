import type {
  EvaluatorSpec,
  EvaluatorType,
  ExecutionBackend,
  RunRequest,
} from "@/lib/api/types";
import {
  OLLAMA_DEFAULT_BASE_URL,
  OLLAMA_DEFAULT_TIMEOUT_SECONDS,
} from "@/lib/api/types";

/** What authored ground truth an evaluator needs on every case. Frontend
 * guidance only — the backend is authoritative and rejects a mismatch (422). */
export type EvaluatorLabelNeed =
  | "none"
  | "reference" // expected_output
  | "retrieval_ids" // expected_retrieval_ids
  | "tool_names" // expected_tool_calls
  | "tool_args"; // expected_tool_calls with explicit arguments

export interface EvaluatorMeta {
  type: EvaluatorType;
  label: string;
  help: string;
  needs: EvaluatorLabelNeed;
  /** The EvaluatorSpec key for this type's pass threshold, if it has one. */
  thresholdKey?: "min_recall" | "min_precision" | "min_groundedness" | "min_score";
  thresholdLabel?: string;
  thresholdDefault?: string;
}

export const EVALUATOR_META: Record<EvaluatorType, EvaluatorMeta> = {
  exact_match: {
    type: "exact_match",
    label: "Exact match",
    help: "Passes when the output equals each case's expected output.",
    needs: "reference",
  },
  contains: {
    type: "contains",
    label: "Contains",
    help: "Passes when the output contains each case's expected output.",
    needs: "reference",
  },
  regex_match: {
    type: "regex_match",
    label: "Regex match",
    help: "Passes when the pattern is found in the output (re.search).",
    needs: "none",
  },
  retrieval_recall: {
    type: "retrieval_recall",
    label: "Retrieval recall",
    help: "Fraction of a case's relevant document/chunk ids that were retrieved.",
    needs: "retrieval_ids",
    thresholdKey: "min_recall",
    thresholdLabel: "min_recall",
    thresholdDefault: "1.0",
  },
  context_precision: {
    type: "context_precision",
    label: "Context precision",
    help: "Fraction of retrieved documents/chunks that are relevant.",
    needs: "retrieval_ids",
    thresholdKey: "min_precision",
    thresholdLabel: "min_precision",
    thresholdDefault: "1.0",
  },
  groundedness: {
    type: "groundedness",
    label: "Answer groundedness (lexical)",
    help: "Lexical-overlap approximation of how much of the answer is supported by retrieved context. Not a hallucination detector.",
    needs: "none",
    thresholdKey: "min_groundedness",
    thresholdLabel: "min_groundedness",
    thresholdDefault: "0.8",
  },
  tool_selection: {
    type: "tool_selection",
    label: "Tool selection",
    help: "Name-set overlap of expected vs observed tools (order-independent).",
    needs: "tool_names",
    thresholdKey: "min_score",
    thresholdLabel: "min_score",
    thresholdDefault: "1.0",
  },
  tool_arguments: {
    type: "tool_arguments",
    label: "Tool arguments",
    help: "Structural (key-order-independent) match of observed tool arguments against the labelled ones. Not semantic.",
    needs: "tool_args",
    thresholdKey: "min_score",
    thresholdLabel: "min_score",
    thresholdDefault: "1.0",
  },
  tool_success: {
    type: "tool_success",
    label: "Tool success",
    help: "Fraction of observed tool calls that succeeded. Needs no labels.",
    needs: "none",
    thresholdKey: "min_score",
    thresholdLabel: "min_score",
    thresholdDefault: "1.0",
  },
  tool_trajectory: {
    type: "tool_trajectory",
    label: "Tool trajectory",
    help: "Ordered adherence of the observed tool-name sequence to the expected one. Exact adherence, not task correctness.",
    needs: "tool_names",
    thresholdKey: "min_score",
    thresholdLabel: "min_score",
    thresholdDefault: "1.0",
  },
};

export const RAG_EVALUATOR_TYPES: readonly EvaluatorType[] = [
  "retrieval_recall",
  "context_precision",
  "groundedness",
];
export const AGENT_EVALUATOR_TYPES: readonly EvaluatorType[] = [
  "tool_selection",
  "tool_arguments",
  "tool_success",
  "tool_trajectory",
];

export interface EvaluatorRow {
  type: EvaluatorType;
  name: string;
  caseSensitive: boolean;
  pattern: string;
  /** Free-form pass threshold; blank = use the backend default. */
  threshold: string;
}

export interface RunConfigState {
  backend: ExecutionBackend;
  baseUrl: string;
  timeoutSeconds: string;
  evaluators: EvaluatorRow[];
}

/** Default case_sensitive per evaluator type — matches the Python evaluators. */
export function defaultCaseSensitive(type: EvaluatorType): boolean {
  return type === "exact_match";
}

export function newEvaluatorRow(type: EvaluatorType = "contains"): EvaluatorRow {
  return {
    type,
    name: "",
    caseSensitive: defaultCaseSensitive(type),
    pattern: "",
    threshold: EVALUATOR_META[type].thresholdDefault ?? "",
  };
}

/** Effective evaluator name the API will use (blank falls back to the type). */
export function effectiveEvaluatorName(row: EvaluatorRow): string {
  return row.name.trim() || row.type;
}

export interface RunConfigErrors {
  evaluators: string | null;
  rows: Array<string | null>;
  ollama: string | null;
}

function thresholdError(row: EvaluatorRow): string | null {
  const meta = EVALUATOR_META[row.type];
  if (!meta.thresholdKey || row.threshold.trim() === "") return null;
  const value = Number(row.threshold);
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    return `${meta.thresholdLabel} must be a number between 0 and 1.`;
  }
  return null;
}

export function validateRunConfig(state: RunConfigState): RunConfigErrors {
  const rows = state.evaluators.map((row) => {
    if (row.type === "regex_match" && row.pattern.trim() === "") {
      return "Pattern is required for regex_match.";
    }
    return thresholdError(row);
  });

  let evaluators: string | null = null;
  if (state.evaluators.length === 0) {
    evaluators = "Add at least one evaluator.";
  } else {
    const names = state.evaluators.map(effectiveEvaluatorName);
    if (new Set(names).size !== names.length) {
      evaluators = "Evaluator names must be unique.";
    }
  }

  let ollama: string | null = null;
  if (state.backend === "ollama") {
    const timeout = Number(state.timeoutSeconds);
    if (state.baseUrl.trim() === "") {
      ollama = "Base URL is required.";
    } else if (
      state.timeoutSeconds.trim() === "" ||
      Number.isNaN(timeout) ||
      timeout <= 0
    ) {
      ollama = "Timeout must be a number greater than 0.";
    }
  }

  return { evaluators, rows, ollama };
}

export function isRunConfigValid(errors: RunConfigErrors): boolean {
  return (
    errors.evaluators === null &&
    errors.ollama === null &&
    errors.rows.every((row) => row === null)
  );
}

/** Serialize form state into the POST /experiments/{id}/run body. Only the
 * fields each evaluator type supports are included (the API forbids extras). */
export function buildRunRequest(state: RunConfigState): RunRequest {
  const evaluators: EvaluatorSpec[] = state.evaluators.map((row) => {
    const meta = EVALUATOR_META[row.type];
    const spec: EvaluatorSpec = { type: row.type };
    const name = row.name.trim();
    if (name !== "") spec.name = name;
    if (row.type === "exact_match" || row.type === "contains") {
      spec.case_sensitive = row.caseSensitive;
    }
    if (row.type === "regex_match") {
      spec.pattern = row.pattern;
    }
    if (meta.thresholdKey && row.threshold.trim() !== "") {
      spec[meta.thresholdKey] = Number(row.threshold);
    }
    return spec;
  });

  if (state.backend === "ollama") {
    const timeout = Number(state.timeoutSeconds);
    return {
      execution: {
        backend: "ollama",
        base_url: state.baseUrl.trim() || OLLAMA_DEFAULT_BASE_URL,
        timeout_seconds: Number.isFinite(timeout)
          ? timeout
          : OLLAMA_DEFAULT_TIMEOUT_SECONDS,
      },
      evaluators,
    };
  }

  return { execution: { backend: "mock" }, evaluators };
}
