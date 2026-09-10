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
  traces: {
    forProject: (projectId: string) =>
      ["projects", projectId, "traces"] as const,
    detail: (id: string) => ["traces", id] as const,
  },
  systemVersions: {
    forProject: (projectId: string) =>
      ["projects", projectId, "system-versions"] as const,
    detail: (id: string) => ["system-versions", id] as const,
  },
  releasePolicies: {
    all: ["release-policies"] as const,
  },
  judgeCalibrations: {
    all: ["judge-calibrations"] as const,
    detail: (id: string) => ["judge-calibrations", id] as const,
  },
  experiments: {
    forProject: (projectId: string) =>
      ["projects", projectId, "experiments"] as const,
    detail: (id: string) => ["experiments", id] as const,
    runs: (id: string) => ["experiments", id, "runs"] as const,
    results: (id: string) => ["experiments", id, "results"] as const,
    diagnostics: (id: string) => ["experiments", id, "diagnostics"] as const,
  },
  jobs: {
    detail: (id: string) => ["jobs", id] as const,
  },
} as const;
