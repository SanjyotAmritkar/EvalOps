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

export interface EvaluatorRow {
  type: EvaluatorType;
  name: string;
  caseSensitive: boolean;
  pattern: string;
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

export function validateRunConfig(state: RunConfigState): RunConfigErrors {
  const rows = state.evaluators.map((row) => {
    if (row.type === "regex_match" && row.pattern.trim() === "") {
      return "Pattern is required for regex_match.";
    }
    return null;
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
    const spec: EvaluatorSpec = { type: row.type };
    const name = row.name.trim();
    if (name !== "") spec.name = name;
    if (row.type === "exact_match" || row.type === "contains") {
      spec.case_sensitive = row.caseSensitive;
    }
    if (row.type === "regex_match") {
      spec.pattern = row.pattern;
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
