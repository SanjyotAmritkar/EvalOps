"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { ChevronRightIcon } from "@/components/icons";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageContainer } from "@/components/layout/page-container";
import { Button, LinkButton } from "@/components/ui/button";
import { Steps } from "@/components/ui/steps";
import { TextField } from "@/components/ui/text-field";
import { useToast } from "@/components/ui/toast";
import { apiErrorMessage } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { useCreateProject, useProjects } from "@/lib/query/projects";

const HOW_IT_WORKS = [
  {
    title: "Dataset",
    description: "Define the behaviour you expect with a fixed set of cases.",
  },
  {
    title: "System versions",
    description: "Pick a baseline (production today) and a candidate (your change).",
  },
  {
    title: "Evaluate",
    description: "Score the output, and — where relevant — retrieval and tool use.",
  },
  {
    title: "Analyze",
    description: "Compare quality, reliability, latency, and cost with statistical evidence.",
  },
  {
    title: "Release",
    description: "A release policy turns the comparison into a PASS or a BLOCK.",
  },
];

export default function ProjectsPage() {
  const projects = useProjects();
  const createProject = useCreateProject();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

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
      {
        onSuccess: (project) => {
          setName("");
          toast(`Project “${project.name}” created`);
        },
      },
    );
  }

  const list = projects.data ?? [];

  return (
    <PageContainer className="flex flex-col gap-12">
      <section className="flex flex-col gap-5">
        <h1 className="max-w-3xl text-[32px] font-semibold leading-tight tracking-tight text-fg sm:text-[38px]">
          Ship AI system changes with confidence.
        </h1>
        <p className="max-w-2xl text-lg leading-relaxed text-fg-muted">
          Compare a candidate against the current AI system and catch quality,
          reliability, latency, and cost regressions before release.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="lg"
            onClick={() => nameInputRef.current?.focus()}
          >
            Create project
          </Button>
          <LinkButton size="lg" variant="secondary" href="#how-it-works">
            How EvalOps works
          </LinkButton>
        </div>
      </section>

      <section id="how-it-works" className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold text-fg">How EvalOps works</h2>
        <div className="rounded-lg border border-border bg-surface p-6 sm:p-7">
          <Steps steps={HOW_IT_WORKS} />
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold text-fg">Projects</h2>
          <p className="text-[15px] text-fg-muted">
            A project groups the datasets, system versions, and experiments for
            one AI application.
          </p>
        </div>

        <form
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-end sm:p-5"
          onSubmit={handleSubmit}
          noValidate
        >
          <div className="flex-1">
            <TextField
              ref={nameInputRef}
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
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {list.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${project.id}`}
                  className="group flex items-center justify-between gap-4 bg-surface px-4 py-3.5 transition-colors hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-[16px] font-medium text-fg">
                      {project.name}
                    </span>
                    <span className="truncate text-[13px] text-fg-subtle">
                      Created {formatDateTime(project.created_at)}
                    </span>
                  </span>
                  <ChevronRightIcon
                    width={18}
                    height={18}
                    className="shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-fg-muted"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </PageContainer>
  );
}
