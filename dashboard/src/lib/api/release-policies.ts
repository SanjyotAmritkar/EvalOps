import { apiFetch } from "./client";
import type { ReleasePolicy, ReleasePolicyCreate } from "./types";

export function listReleasePolicies(): Promise<ReleasePolicy[]> {
  return apiFetch<ReleasePolicy[]>("/release-policies");
}

export function createReleasePolicy(
  body: ReleasePolicyCreate,
): Promise<ReleasePolicy> {
  return apiFetch<ReleasePolicy>("/release-policies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
