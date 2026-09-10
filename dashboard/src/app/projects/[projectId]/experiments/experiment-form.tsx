"use client";

import { useState, type FormEvent } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { TextField } from "@/components/ui/text-field";
import { RoleChip } from "@/components/ui/role-chip";
import { ApiError } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { Experiment } from "@/lib/api/types";
import { useDatasets } from "@/lib/query/datasets";
import { useCreateExperiment } from "@/lib/query/experiments";
import { useReleasePolicies } from "@/lib/query/release-policies";
import { useSystemVersions } from "@/lib/query/system-versions";

export function ExperimentForm({
  projectId,
  onCreated,
  initialDatasetId,
}: {
  projectId: string;
  onCreated: (experiment: Experiment) => void;
  /** Preselect this dataset (e.g. a replay dataset promoted from traces). */
  initialDatasetId?: string;
}) {
  const datasets = useDatasets(projectId);
  const systemVersions = useSystemVersions(projectId);
  const releasePolicies = useReleasePolicies();
  const create = useCreateExperiment(projectId);

  const [datasetId, setDatasetId] = useState(initialDatasetId ?? "");
  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [policyId, setPolicyId] = useState("");
  const [repeats, setRepeats] = useState("1");

  const datasetList = datasets.data ?? [];
  const versionList = systemVersions.data ?? [];
  const policyList = releasePolicies.data ?? [];

  const notEnough =
    !datasets.isPending &&
    !systemVersions.isPending &&
    (datasetList.length === 0 || versionList.length < 2);

  const repeatsNumber = Number.parseInt(repeats, 10);
  const repeatsValid = Number.isInteger(repeatsNumber) && repeatsNumber >= 1;
  const sameVersion = baselineId !== "" && baselineId === candidateId;

  const canSubmit =
    datasetId !== "" &&
    baselineId !== "" &&
    candidateId !== "" &&
    !sameVersion &&
    repeatsValid &&
    !create.isPending;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      {
        dataset_id: datasetId,
        baseline_version_id: baselineId,
        candidate_version_id: candidateId,
        release_policy_id: policyId === "" ? null : policyId,
        repeats: repeatsNumber,
      },
      { onSuccess: (experiment) => onCreated(experiment) },
    );
  }

  if (notEnough) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-border bg-surface p-4">
        <p className="text-sm font-medium text-fg">
          Not enough resources to define an experiment
        </p>
        <p className="text-sm text-fg-muted">
          An experiment compares two system versions over a dataset. This project
          has {datasetList.length} dataset
          {datasetList.length === 1 ? "" : "s"} and {versionList.length} system
          version{versionList.length === 1 ? "" : "s"}.
        </p>
        <div className="flex flex-wrap gap-2">
          <LinkButton
            variant="secondary"
            href={`/projects/${projectId}/datasets`}
          >
            Add dataset
          </LinkButton>
          <LinkButton
            variant="secondary"
            href={`/projects/${projectId}/system-versions`}
          >
            Add system version
          </LinkButton>
        </div>
      </div>
    );
  }

  const versionLabel = (id: string) => {
    const version = versionList.find((v) => v.id === id);
    return version
      ? `${version.name} ${version.version} — ${version.provider}/${version.model}`
      : "";
  };

  return (
    <Card className="p-5">
      <form className="flex flex-col gap-6" onSubmit={submit} noValidate>
        <p className="text-sm text-fg-muted">
          Run your current system (
          <span className="font-medium text-fg">baseline</span>) and a proposed
          change (<span className="font-medium text-accent">candidate</span>) over
          the same dataset, then compare them.
        </p>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-semibold text-fg">
            What you&rsquo;re comparing
          </legend>
          <div className="flex items-center gap-2 text-xs font-medium text-fg-subtle">
            <span>Baseline</span>
            <span aria-hidden>→</span>
            <span className="text-accent">Candidate</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2 border-l-2 border-border pl-3">
              <RoleChip role="baseline" />
              <span className="text-xs text-fg-subtle">Current configuration</span>
              <Select
                label="Baseline system version"
                value={baselineId}
                onChange={(event) => setBaselineId(event.target.value)}
                disabled={create.isPending}
              >
                <option value="">Select…</option>
                {versionList.map((version) => (
                  <option key={version.id} value={version.id}>
                    {versionLabel(version.id)}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-2 border-l-2 border-accent pl-3">
              <RoleChip role="candidate" />
              <span className="text-xs text-fg-subtle">Proposed change</span>
              <Select
                label="Candidate system version"
                value={candidateId}
                onChange={(event) => setCandidateId(event.target.value)}
                disabled={create.isPending}
              >
                <option value="">Select…</option>
                {versionList.map((version) => (
                  <option key={version.id} value={version.id}>
                    {versionLabel(version.id)}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          {sameVersion ? (
            <p className="text-xs text-block">
              Baseline and candidate must be different system versions.
            </p>
          ) : null}
        </fieldset>

        <fieldset className="flex flex-col gap-4">
          <legend className="text-sm font-semibold text-fg">
            Evaluation setup
          </legend>
          <Select
            label="Dataset"
            value={datasetId}
            onChange={(event) => setDatasetId(event.target.value)}
            hint="The fixed set of cases both versions are evaluated on."
            disabled={create.isPending}
          >
            <option value="">Select a dataset…</option>
            {datasetList.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name} v{dataset.version} · {dataset.cases.length} case
                {dataset.cases.length === 1 ? "" : "s"}
              </option>
            ))}
          </Select>
          <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
            <Select
              label="Release policy (optional)"
              value={policyId}
              onChange={(event) => setPolicyId(event.target.value)}
              hint="Decides PASS / BLOCK. Without one, the run is a comparison only."
              disabled={create.isPending}
            >
              <option value="">None</option>
              {policyList.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policy.name}
                </option>
              ))}
            </Select>
            <TextField
              label="Repeats"
              type="number"
              min={1}
              step={1}
              value={repeats}
              onChange={(event) => setRepeats(event.target.value)}
              error={
                repeats !== "" && !repeatsValid ? "Whole number ≥ 1" : undefined
              }
              hint="Runs per case, per version."
              disabled={create.isPending}
            />
          </div>
        </fieldset>

        {create.isError ? (
          <p className="text-sm text-block">
            {create.error instanceof ApiError && create.error.status === 409
              ? "An identical experiment already exists."
              : apiErrorMessage(
                  create.error,
                  "Could not create the experiment.",
                )}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Creating…" : "Create experiment"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
