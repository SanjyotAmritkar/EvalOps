import { apiFetch } from "./client";
import type { SystemVersion, SystemVersionCreate } from "./types";

export function listSystemVersions(projectId: string): Promise<SystemVersion[]> {
  return apiFetch<SystemVersion[]>(`/projects/${projectId}/system-versions`);
}

export function getSystemVersion(id: string): Promise<SystemVersion> {
  return apiFetch<SystemVersion>(`/system-versions/${id}`);
}

export function createSystemVersion(
  projectId: string,
  body: SystemVersionCreate,
): Promise<SystemVersion> {
  return apiFetch<SystemVersion>(`/projects/${projectId}/system-versions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
