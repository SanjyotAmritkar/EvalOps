import { apiFetch } from "./client";
import type { Project, ProjectCreate } from "./types";

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}`);
}

export function createProject(body: ProjectCreate): Promise<Project> {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
