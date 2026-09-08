const API_BASE = "/api";

export interface FieldError {
  /** Dotted path to the offending field, e.g. "name" or "cases.0.input". */
  field: string;
  message: string;
}

/** Normalized error for any non-2xx API response. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly fieldErrors: FieldError[];
  readonly raw: unknown;

  constructor(
    status: number,
    detail: string,
    fieldErrors: FieldError[] = [],
    raw?: unknown,
  ) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.raw = raw;
  }
}

interface FastApiValidationItem {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

function toFieldError(item: FastApiValidationItem): FieldError {
  const loc = Array.isArray(item.loc) ? item.loc : [];
  // FastAPI prefixes the location with "body" / "query" / "path"; drop it.
  const path = (loc.length > 1 ? loc.slice(1) : loc).join(".");
  return { field: path, message: item.msg ?? "Invalid value" };
}

function normalizeError(
  status: number,
  statusText: string,
  body: unknown,
): ApiError {
  if (body !== null && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;

    if (typeof detail === "string") {
      return new ApiError(status, detail, [], body);
    }

    if (Array.isArray(detail)) {
      const fieldErrors = detail.map((item) =>
        toFieldError(item as FastApiValidationItem),
      );
      const summary =
        fieldErrors
          .map((e) => (e.field ? `${e.field}: ${e.message}` : e.message))
          .join("; ") || "Validation failed";
      return new ApiError(status, summary, fieldErrors, body);
    }
  }

  return new ApiError(
    status,
    statusText || `Request failed (${status})`,
    [],
    body,
  );
}

/**
 * Fetch JSON from the EvalOps API. Requests go through the same-origin `/api`
 * proxy (see next.config.ts). Non-2xx responses throw {@link ApiError}.
 */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw normalizeError(response.status, response.statusText, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
