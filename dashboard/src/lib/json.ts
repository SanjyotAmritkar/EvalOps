export interface JsonObjectResult {
  /** Parsed object, or null when the input is blank or invalid. */
  value: Record<string, unknown> | null;
  /** Human-readable reason the input is not a JSON object, or null. */
  error: string | null;
}

/** Parse a text field that should hold a JSON object. Blank input is valid (null). */
export function parseJsonObject(text: string): JsonObjectResult {
  const trimmed = text.trim();
  if (trimmed === "") return { value: null, error: null };

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { value: null, error: "not valid JSON" };
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { value: null, error: "must be a JSON object" };
  }

  return { value: parsed as Record<string, unknown>, error: null };
}

/** Pretty-print a value as 2-space JSON. */
export function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
