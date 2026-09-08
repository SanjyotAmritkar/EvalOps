export const queryKeys = {
  projects: {
    all: ["projects"] as const,
    detail: (id: string) => ["projects", id] as const,
  },
  datasets: {
    forProject: (projectId: string) =>
      ["projects", projectId, "datasets"] as const,
    detail: (id: string) => ["datasets", id] as const,
  },
  systemVersions: {
    forProject: (projectId: string) =>
      ["projects", projectId, "system-versions"] as const,
    detail: (id: string) => ["system-versions", id] as const,
  },
  releasePolicies: {
    all: ["release-policies"] as const,
  },
  experiments: {
    forProject: (projectId: string) =>
      ["projects", projectId, "experiments"] as const,
  },
} as const;
