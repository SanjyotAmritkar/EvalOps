"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageContainer } from "@/components/layout/page-container";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextField } from "@/components/ui/text-field";
import { ChevronRightIcon } from "@/components/icons";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useCreateProject, useProjects } from "@/lib/query/projects";

export default function ProjectsPage() {
  const projects = useProjects();
  const createProject = useCreateProject();
  const [name, setName] = useState("");

  const trimmed = name.trim();
  const canSubmit = trimmed.length > 0 && !createProject.isPending;

  const createError = createProject.isError
    ? apiErrorMessage(
        createProject.error,
        "Could not create the project. Check that the API is running.",
      )
    : undefined;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    createProject.mutate(
      { name: trimmed },
      { onSuccess: () => setName("") },
    );
  }

  const list = projects.data ?? [];

  return (
    <PageContainer className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight text-fg">
          Projects
        </h1>
        <p className="text-sm text-fg-muted">
          A project groups the datasets, system versions, and experiments for one
          AI application.
        </p>
      </header>

      <Card className="p-4">
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={handleSubmit}
          noValidate
        >
          <div className="flex-1">
            <TextField
              label="New project"
              placeholder="e.g. Support Assistant"
              value={name}
              onChange={(event) => setName(event.target.value)}
              error={createError}
              disabled={createProject.isPending}
              autoComplete="off"
            />
          </div>
          <Button type="submit" disabled={!canSubmit}>
            {createProject.isPending ? "Creating…" : "Create project"}
          </Button>
        </form>
      </Card>

      {projects.isPending ? (
        <LoadingState />
      ) : projects.isError ? (
        <ErrorState
          title="Could not load projects"
          message={apiErrorMessage(
            projects.error,
            "The API did not respond. Confirm the FastAPI server is running and reachable.",
          )}
          onRetry={() => void projects.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No projects yet"
          description="Create your first project above to start tracking evaluations."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {list.map((project) => (
            <li key={project.id}>
              <Link
                href={`/projects/${project.id}`}
                className="group flex items-center justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-fg-subtle/40 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate font-medium text-fg">
                    {project.name}
                  </span>
                  <span className="truncate text-xs text-fg-subtle">
                    Created {formatDateTime(project.created_at)}
                  </span>
                </span>
                <ChevronRightIcon
                  width={16}
                  height={16}
                  className="shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-fg-muted"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
