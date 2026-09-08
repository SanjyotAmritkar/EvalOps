"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { ErrorState } from "@/components/feedback/error-state";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { PageContainer } from "@/components/layout/page-container";
import { WorkspaceTabs } from "@/components/layout/workspace-tabs";
import { CopyButton } from "@/components/ui/copy-button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import { useProject } from "@/lib/query/projects";

export default function ProjectWorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const project = useProject(projectId);

  if (project.isError) {
    const notFound = isNotFound(project.error);
    return (
      <PageContainer className="flex flex-col gap-4">
        <Breadcrumbs
          items={[
            { label: "Projects", href: "/projects" },
            { label: notFound ? "Not found" : "Error" },
          ]}
        />
        <ErrorState
          title={notFound ? "Project not found" : "Could not load project"}
          message={
            notFound
              ? "This project does not exist or was removed."
              : apiErrorMessage(
                  project.error,
                  "The API did not respond. Confirm the FastAPI server is running.",
                )
          }
          onRetry={notFound ? undefined : () => void project.refetch()}
        />
        <Link
          href="/projects"
          className="text-sm text-accent transition-colors hover:underline"
        >
          ← Back to projects
        </Link>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Breadcrumbs
          items={[
            { label: "Projects", href: "/projects" },
            { label: project.data?.name ?? "…" },
          ]}
        />
        {project.isPending || !project.data ? (
          <Skeleton className="h-7 w-56" />
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-xl font-semibold tracking-tight text-fg">
              {project.data.name}
            </h1>
            <span className="inline-flex items-center gap-1.5">
              <code className="font-mono text-xs text-fg-subtle">
                {project.data.id}
              </code>
              <CopyButton value={project.data.id} label="Copy ID" />
            </span>
          </div>
        )}
      </div>

      <WorkspaceTabs projectId={projectId} />

      <div>{children}</div>
    </PageContainer>
  );
}
