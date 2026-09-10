"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { LinkButton } from "@/components/ui/button";
import { Steps } from "@/components/ui/steps";
import { WorkflowSteps } from "@/components/ui/workflow-steps";
import { formatDateTime, shortId } from "@/lib/format";
import { useDatasets } from "@/lib/query/datasets";
import { useExperiments } from "@/lib/query/experiments";
import { useProject } from "@/lib/query/projects";
import { useSystemVersions } from "@/lib/query/system-versions";

export default function ProjectOverviewPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = String(params.projectId ?? "");
  const base = `/projects/${projectId}`;

  const project = useProject(projectId);
  const datasets = useDatasets(projectId);
  const versions = useSystemVersions(projectId);
  const experiments = useExperiments(projectId);

  const datasetCount = datasets.data?.length ?? 0;
  const versionCount = versions.data?.length ?? 0;
  const experimentCount = experiments.data?.length ?? 0;
  const readyToRun = datasetCount >= 1 && versionCount >= 2;

  const recentExperiments = [...(experiments.data ?? [])]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 3);

  const versionName = (id: string) => {
    const match = versions.data?.find((v) => v.id === id);
    return match ? `${match.name} ${match.version}` : shortId(id);
  };
  const datasetName = (id: string) =>
    datasets.data?.find((d) => d.id === id)?.name ?? shortId(id);

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        title="Overview"
        description={`Everything for ${
          project.data?.name ?? "this project"
        } in one place — compare a candidate against your current AI system and decide whether it is safe to ship.`}
        actions={
          readyToRun ? (
            <LinkButton href={`${base}/experiments`}>Run evaluation</LinkButton>
          ) : (
            <LinkButton href={`${base}/datasets`}>Add a dataset</LinkButton>
          )
        }
      />

      <section className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5 sm:p-6">
        <h2 className="text-base font-semibold text-fg">How it fits together</h2>
        <WorkflowSteps
          steps={[
            { label: "Dataset" },
            { label: "Baseline" },
            { label: "Candidate", tone: "candidate" },
            { label: "Evaluation" },
            { label: "Release decision" },
          ]}
        />
        <p className="text-[14px] leading-relaxed text-fg-muted">
          An experiment runs the baseline and the candidate over one dataset;
          the release policy turns the comparison into a PASS or a BLOCK.
        </p>
      </section>

      <section className="flex flex-col gap-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold text-fg">Setup</h2>
          <span className="text-[13px] text-fg-subtle">
            {datasetCount} dataset{datasetCount === 1 ? "" : "s"} ·{" "}
            {versionCount} system version{versionCount === 1 ? "" : "s"} ·{" "}
            {experimentCount} experiment{experimentCount === 1 ? "" : "s"}
          </span>
        </div>
        <div className="rounded-lg border border-border bg-surface p-5 sm:p-6">
          <Steps
            showStatus
            steps={[
              {
                title: "Add a dataset",
                done: datasetCount >= 1,
                description: (
                  <Link
                    href={`${base}/datasets`}
                    className="text-accent hover:underline"
                  >
                    {datasetCount >= 1
                      ? `${datasetCount} added — manage datasets`
                      : "Define the behaviour you expect →"}
                  </Link>
                ),
              },
              {
                title: "Add a baseline and a candidate system version",
                done: versionCount >= 2,
                description: (
                  <Link
                    href={`${base}/system-versions`}
                    className="text-accent hover:underline"
                  >
                    {versionCount >= 2
                      ? `${versionCount} added — manage system versions`
                      : `${versionCount} of 2 — add system versions →`}
                  </Link>
                ),
              },
              {
                title: "Define an experiment",
                done: experimentCount >= 1,
                description: (
                  <Link
                    href={`${base}/experiments`}
                    className="text-accent hover:underline"
                  >
                    {experimentCount >= 1
                      ? `${experimentCount} defined — manage experiments`
                      : "Pair the versions over a dataset →"}
                  </Link>
                ),
              },
              {
                title: "Run it and review the release decision",
                done: false,
                description:
                  "Execution is asynchronous; the decision and statistical evidence appear on the experiment page.",
              },
            ]}
          />
        </div>
      </section>

      {recentExperiments.length > 0 ? (
        <section className="flex flex-col gap-4">
          <h2 className="text-xl font-semibold text-fg">Recent experiments</h2>
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {recentExperiments.map((experiment) => (
              <li key={experiment.id}>
                <Link
                  href={`${base}/experiments/${experiment.id}`}
                  className="flex flex-col gap-1 bg-surface px-4 py-3.5 transition-colors hover:bg-surface-raised sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="text-[15px] text-fg">
                    {versionName(experiment.baseline_version_id)}{" "}
                    <span aria-hidden className="text-fg-subtle">
                      →
                    </span>{" "}
                    <span className="text-accent">
                      {versionName(experiment.candidate_version_id)}
                    </span>
                  </span>
                  <span className="text-[13px] text-fg-subtle">
                    {datasetName(experiment.dataset_id)} ·{" "}
                    {formatDateTime(experiment.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
