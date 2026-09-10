"use client";

import { useState, type FormEvent } from "react";
import { PlusIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextField } from "@/components/ui/text-field";
import { apiErrorMessage } from "@/lib/api/errors";
import { KNOWN_POLICY_METRICS } from "@/lib/metrics";
import { useCreateReleasePolicy } from "@/lib/query/release-policies";
import { useToast } from "@/components/ui/toast";

interface ThresholdRow {
  metric: string;
  value: string;
}

const emptyRow: ThresholdRow = { metric: "", value: "" };

export function ReleasePolicyForm({ onCreated }: { onCreated: () => void }) {
  const create = useCreateReleasePolicy();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [rows, setRows] = useState<ThresholdRow[]>([{ ...emptyRow }]);
  const [safety, setSafety] = useState("0");

  const filledRows = rows
    .map((row) => ({ metric: row.metric.trim(), value: row.value.trim() }))
    .filter((row) => row.metric !== "" || row.value !== "");

  const rowIssues = filledRows.map((row) => {
    if (row.metric === "") return "metric name is required";
    const parsed = Number(row.value);
    if (row.value === "" || Number.isNaN(parsed) || parsed < 0) {
      return "value must be a number ≥ 0";
    }
    return null;
  });
  const duplicateMetric =
    new Set(filledRows.map((row) => row.metric)).size !== filledRows.length;

  const safetyNumber = Number.parseInt(safety, 10);
  const safetyValid = Number.isInteger(safetyNumber) && safetyNumber >= 0;

  const canSubmit =
    name.trim().length > 0 &&
    rowIssues.every((issue) => issue === null) &&
    !duplicateMetric &&
    safetyValid &&
    !create.isPending;

  function updateRow(index: number, patch: Partial<ThresholdRow>) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    const thresholds: Record<string, number> = {};
    for (const row of filledRows) thresholds[row.metric] = Number(row.value);
    create.mutate(
      {
        name: name.trim(),
        thresholds,
        max_safety_violations: safetyNumber,
      },
      {
        onSuccess: () => {
          toast("Release policy created");
          setName("");
          setRows([{ ...emptyRow }]);
          setSafety("0");
          onCreated();
        },
      },
    );
  }

  return (
    <Card className="p-4">
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <TextField
          label="Name"
          placeholder="e.g. default-latency-budget"
          value={name}
          onChange={(event) => setName(event.target.value)}
          autoComplete="off"
          disabled={create.isPending}
        />

        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-fg">
            Thresholds
          </legend>
          <p className="text-xs text-fg-subtle">
            Maximum tolerated adverse change per metric, as a fraction:{" "}
            <span className="font-mono">0.10</span> allows a 10% regression.
            Known metrics: <span className="font-mono">success_rate</span>,{" "}
            <span className="font-mono">latency_ms.mean</span>,{" "}
            <span className="font-mono">latency_ms.p95</span>,{" "}
            <span className="font-mono">cost_usd.total</span>, and{" "}
            <span className="font-mono">&lt;evaluator&gt;.pass_rate</span>.
          </p>

          <datalist id="known-policy-metrics">
            {KNOWN_POLICY_METRICS.map((metric) => (
              <option key={metric} value={metric} />
            ))}
          </datalist>

          <div className="flex flex-col gap-2">
            {rows.map((row, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  list="known-policy-metrics"
                  aria-label={`Threshold ${index + 1} metric`}
                  placeholder="metric"
                  value={row.metric}
                  onChange={(event) =>
                    updateRow(index, { metric: event.target.value })
                  }
                  disabled={create.isPending}
                  className="h-9 flex-1 rounded-md border border-border bg-surface px-3 font-mono text-[13px] text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  aria-label={`Threshold ${index + 1} value`}
                  placeholder="0.10"
                  value={row.value}
                  onChange={(event) =>
                    updateRow(index, { value: event.target.value })
                  }
                  disabled={create.isPending}
                  className="h-9 w-28 rounded-md border border-border bg-surface px-3 text-sm tabular-nums text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() =>
                    setRows((current) =>
                      current.length === 1
                        ? [{ ...emptyRow }]
                        : current.filter((_, i) => i !== index),
                    )
                  }
                  disabled={create.isPending}
                  aria-label={`Remove threshold ${index + 1}`}
                  className="h-9 rounded-md border border-border px-2 text-xs text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg disabled:opacity-50"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setRows((current) => [...current, { ...emptyRow }])}
            disabled={create.isPending}
            className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-accent transition-colors hover:underline disabled:opacity-50"
          >
            <PlusIcon width={13} height={13} />
            Add threshold
          </button>

          {duplicateMetric ? (
            <p className="text-xs text-block">
              Each metric can appear only once.
            </p>
          ) : null}
        </fieldset>

        <TextField
          label="Safety-violation limit"
          type="number"
          min={0}
          step={1}
          value={safety}
          onChange={(event) => setSafety(event.target.value)}
          error={!safetyValid ? "Whole number ≥ 0" : undefined}
          hint="Safety metrics are not evaluated yet, so this limit currently has no effect."
          disabled={create.isPending}
        />

        {create.isError ? (
          <p className="text-sm text-block">
            {apiErrorMessage(
              create.error,
              "Could not create the release policy.",
            )}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Creating…" : "Create policy"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
