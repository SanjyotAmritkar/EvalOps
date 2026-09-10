"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ErrorState } from "@/components/feedback/error-state";
import { ArrowLeftIcon, MenuIcon } from "@/components/icons";
import {
  ProjectNav,
  activeSectionLabel,
} from "@/components/layout/project-nav";
import { CopyButton } from "@/components/ui/copy-button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiErrorMessage, isNotFound } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useProject } from "@/lib/query/projects";

export default function ProjectWorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const pathname = usePathname() ?? "";
  const project = useProject(projectId);
  const section = activeSectionLabel(pathname, projectId);

  if (project.isError) {
    const notFound = isNotFound(project.error);
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-12 sm:px-8">
        <Link
          href="/projects"
          className="mb-6 inline-flex items-center gap-1.5 text-[14px] text-fg-muted transition-colors hover:text-fg"
        >
          <ArrowLeftIcon width={14} height={14} />
          All projects
        </Link>
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
      </div>
    );
  }

  const name = project.data?.name;

  const sidebar = (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Link
          href="/projects"
          className="inline-flex w-fit items-center gap-1.5 text-[13px] text-fg-muted transition-colors hover:text-fg"
        >
          <ArrowLeftIcon width={13} height={13} />
          All projects
        </Link>
        {project.isPending || !name ? (
          <Skeleton className="h-6 w-40" />
        ) : (
          <h2 className="truncate text-[17px] font-semibold tracking-tight text-fg">
            {name}
          </h2>
        )}
      </div>

      <ProjectNav projectId={projectId} />

      {project.data ? (
        <details className="mt-2 border-t border-border pt-3 text-[13px] text-fg-subtle">
          <summary className="cursor-pointer select-none text-fg-muted">
            Project details
          </summary>
          <div className="mt-2 flex flex-col gap-1.5">
            <span>Created {formatDateTime(project.data.created_at)}</span>
            <span className="inline-flex items-center gap-2">
              <code className="truncate font-mono text-[12px]">
                {project.data.id}
              </code>
              <CopyButton value={project.data.id} label="Copy ID" />
            </span>
          </div>
        </details>
      ) : null}
    </div>
  );

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8 sm:px-8 lg:grid lg:grid-cols-[224px_minmax(0,1fr)] lg:gap-12">
      {/* Mobile: collapsed section menu */}
      <details className="mb-6 rounded-lg border border-border bg-surface lg:hidden">
        <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-3 text-[15px] font-medium text-fg">
          <MenuIcon width={16} height={16} />
          <span className="text-fg-muted">{name ?? "Project"} ·</span>
          {section}
        </summary>
        <div className="border-t border-border px-4 py-4">{sidebar}</div>
      </details>

      {/* Desktop: sticky sidebar */}
      <aside className="hidden lg:block">
        <div className="sticky top-24">{sidebar}</div>
      </aside>

      <div className="min-w-0">{children}</div>
    </div>
  );
}
