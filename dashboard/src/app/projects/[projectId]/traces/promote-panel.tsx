"use client";

import { useState, type FormEvent } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextField } from "@/components/ui/text-field";
import { ApiError } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { ProductionTrace } from "@/lib/api/types";
import { useCreateTraceDataset } from "@/lib/query/traces";

export function PromotePanel({
  projectId,
  selectedTraces,
  onClear,
}: {
  projectId: string;
  selectedTraces: ProductionTrace[];
  onClear: () => void;
}) {
  const create = useCreateTraceDataset(projectId);
  const [name, setName] = useState("");

  const count = selectedTraces.length;
  const withReference = selectedTraces.filter(
    (t) => t.reference_output !== null && t.reference_output.trim() !== "",
  ).length;
  const missingReference = count - withReference;

  const canSubmit = name.trim().length > 0 && count > 0 && !create.isPending;
  const isConflict =
    create.error instanceof ApiError && create.error.status === 409;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    create.mutate({
      name: name.trim(),
      trace_ids: selectedTraces.map((t) => t.id),
    });
  }

  if (create.isSuccess && create.data) {
    const dataset = create.data;
    return (
      <Card className="flex flex-col gap-3 border-pass/30 p-5">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-pass">
            Replay dataset created
          </span>
          <p className="text-sm text-fg">
            <span className="font-medium">{dataset.name}</span> — {dataset.cases.length}{" "}
            case{dataset.cases.length === 1 ? "" : "s"}, each carrying its{" "}
            <code className="font-mono text-[12px]">source_trace_id</code>.
          </p>
        </div>
        <p className="text-sm text-fg-muted">
          Next: create an experiment on this dataset to compare a baseline
          against a candidate and get a PASS / BLOCK release decision.
        </p>
        <div className="flex flex-wrap gap-2">
          <LinkButton
            href={`/projects/${projectId}/experiments?dataset=${dataset.id}`}
          >
            Create experiment with this dataset
          </LinkButton>
          <LinkButton
            variant="secondary"
            href={`/projects/${projectId}/datasets/${dataset.id}`}
          >
            View dataset
          </LinkButton>
          <Button
            variant="ghost"
            onClick={() => {
              create.reset();
              setName("");
              onClear();
            }}
          >
            Promote more traces
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-fg">
            {count} trace{count === 1 ? "" : "s"} selected
          </span>
          <button
            type="button"
            onClick={onClear}
            className="text-xs font-medium text-fg-subtle transition-colors hover:text-fg"
          >
            Clear selection
          </button>
        </div>

        <p className="text-sm text-fg-muted">
          {withReference} of {count} selected trace{count === 1 ? "" : "s"} have
          reference outputs.
        </p>
        {missingReference > 0 ? (
          <p className="rounded-md border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-fg-muted">
            Cases without references can still be replayed, but reference-based
            evaluators may not be applicable. Production output is never used as a
            reference.
          </p>
        ) : null}

        <TextField
          label="Replay dataset name"
          placeholder="e.g. production-regression-set"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="off"
          disabled={create.isPending}
        />

        {create.isError ? (
          <p className="text-sm text-block">
            {isConflict
              ? `A dataset named “${name.trim()}” already exists in this project. Choose another name.`
              : apiErrorMessage(
                  create.error,
                  "Could not create the replay dataset.",
                )}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Creating…" : "Create replay dataset"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
