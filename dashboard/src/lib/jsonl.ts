import type {
  CaseOrigin,
  DatasetCaseInput,
  ExpectedToolCallInput,
} from "@/lib/api/types";

export interface JsonlError {
  line: number;
  message: string;
}

export interface JsonlParseResult {
  cases: DatasetCaseInput[];
  errors: JsonlError[];
}

const ORIGINS: readonly CaseOrigin[] = ["authored", "promoted_trace"];

/**
 * Parse pasted JSONL into dataset-case inputs. One JSON object per line; blank
 * lines are ignored. Structural checks only — semantic rules (e.g. a
 * promoted_trace case needing a source_trace_id) are enforced by the API and
 * surface as a 422.
 */
export function parseCasesJsonl(text: string): JsonlParseResult {
  const cases: DatasetCaseInput[] = [];
  const errors: JsonlError[] = [];

  text.split("\n").forEach((raw, index) => {
    const line = index + 1;
    const trimmed = raw.trim();
    if (trimmed === "") return;

    let value: unknown;
    try {
      value = JSON.parse(trimmed);
    } catch {
      errors.push({ line, message: "not valid JSON" });
      return;
    }

    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      errors.push({ line, message: "expected a JSON object" });
      return;
    }

    const obj = value as Record<string, unknown>;

    if (typeof obj.input !== "string" || obj.input.trim() === "") {
      errors.push({ line, message: '"input" must be a non-empty string' });
      return;
    }

    const parsed: DatasetCaseInput = { input: obj.input };

    if (obj.expected_output !== undefined && obj.expected_output !== null) {
      if (typeof obj.expected_output !== "string") {
        errors.push({ line, message: '"expected_output" must be a string' });
        return;
      }
      parsed.expected_output = obj.expected_output;
    }

    if (obj.origin !== undefined) {
      if (
        typeof obj.origin !== "string" ||
        !ORIGINS.includes(obj.origin as CaseOrigin)
      ) {
        errors.push({
          line,
          message: '"origin" must be "authored" or "promoted_trace"',
        });
        return;
      }
      parsed.origin = obj.origin as CaseOrigin;
    }

    if (obj.source_trace_id !== undefined && obj.source_trace_id !== null) {
      if (typeof obj.source_trace_id !== "string") {
        errors.push({ line, message: '"source_trace_id" must be a string' });
        return;
      }
      parsed.source_trace_id = obj.source_trace_id;
    }

    if (obj.expected_retrieval_ids !== undefined) {
      if (
        !Array.isArray(obj.expected_retrieval_ids) ||
        !obj.expected_retrieval_ids.every(
          (id) => typeof id === "string" && id.trim() !== "",
        )
      ) {
        errors.push({
          line,
          message: '"expected_retrieval_ids" must be a list of non-empty strings',
        });
        return;
      }
      parsed.expected_retrieval_ids = obj.expected_retrieval_ids as string[];
    }

    if (obj.expected_tool_calls !== undefined) {
      const calls = parseExpectedToolCalls(obj.expected_tool_calls);
      if (calls === null) {
        errors.push({
          line,
          message:
            '"expected_tool_calls" must be a list of {"name": string, "arguments"?: object}',
        });
        return;
      }
      parsed.expected_tool_calls = calls;
    }

    cases.push(parsed);
  });

  return { cases, errors };
}

function parseExpectedToolCalls(
  value: unknown,
): ExpectedToolCallInput[] | null {
  if (!Array.isArray(value)) return null;
  const out: ExpectedToolCallInput[] = [];
  for (const entry of value) {
    if (
      typeof entry !== "object" ||
      entry === null ||
      Array.isArray(entry) ||
      typeof (entry as Record<string, unknown>).name !== "string" ||
      ((entry as Record<string, unknown>).name as string).trim() === ""
    ) {
      return null;
    }
    const row = entry as Record<string, unknown>;
    const call: ExpectedToolCallInput = { name: row.name as string };
    if (row.arguments !== undefined && row.arguments !== null) {
      if (
        typeof row.arguments !== "object" ||
        Array.isArray(row.arguments)
      ) {
        return null;
      }
      call.arguments = row.arguments as Record<string, unknown>;
    }
    out.push(call);
  }
  return out;
}
