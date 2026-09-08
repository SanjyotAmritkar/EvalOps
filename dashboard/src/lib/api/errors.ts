import { ApiError } from "./client";

/** ApiError.message when it is one, otherwise the given fallback. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
