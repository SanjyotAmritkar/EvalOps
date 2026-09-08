"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProject,
  getProject,
  listProjects,
} from "@/lib/api/projects";
import type { Project, ProjectCreate } from "@/lib/api/types";
import { queryKeys } from "./keys";

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects.all,
    queryFn: listProjects,
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: queryKeys.projects.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: projectId.length > 0,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation<Project, Error, ProjectCreate>({
    mutationFn: createProject,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.projects.all,
      });
    },
  });
}
