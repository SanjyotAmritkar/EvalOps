"use client";

import { useState, type FormEvent } from "react";
import { Button, LinkButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { TextField } from "@/components/ui/text-field";
import { TextArea } from "@/components/ui/textarea";
import { apiErrorMessage } from "@/lib/api/errors";
import type { TraceCreate } from "@/lib/api/types";
import { useSystemVersions } from "@/lib/query/system-versions";
import { useCreateTrace } from "@/lib/query/traces";

/** Optional numeric field: "" -> undefined; anything non-numeric or < 0 -> invalid. */
function parseOptionalNonNegative(raw: string): {
  value: number | undefined;
  invalid: boolean;
} {
  if (raw.trim() === "") return { value: undefined, invalid: false };
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return { value: undefined, invalid: true };
  return { value: n, invalid: false };
}

export function AddTraceForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const versions = useSystemVersions(projectId);
  const create = useCreateTrace(projectId);

  const [systemVersionId, setSystemVersionId] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [reference, setReference] = useState("");
  const [latency, setLatency] = useState("");
  const [cost, setCost] = useState("");

  const versionList = versions.data ?? [];
  const latencyParsed = parseOptionalNonNegative(latency);
  const costParsed = parseOptionalNonNegative(cost);

  const canSubmit =
    systemVersionId !== "" &&
    input.trim() !== "" &&
    !latencyParsed.invalid &&
    !costParsed.invalid &&
    !create.isPending;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    const body: TraceCreate = {
      system_version_id: systemVersionId,
      input,
      ...(output.trim() !== "" ? { output } : {}),
      ...(reference.trim() !== "" ? { reference_output: reference } : {}),
      ...(latencyParsed.value !== undefined
        ? { latency_ms: latencyParsed.value }
        : {}),
      ...(costParsed.value !== undefined ? { cost_usd: costParsed.value } : {}),
    };
    create.mutate(body, {
      onSuccess: () => {
        setInput("");
        setOutput("");
        setReference("");
        setLatency("");
        setCost("");
        onCreated();
      },
    });
  }

  if (versions.data && versionList.length === 0) {
    return (
      <Card className="flex flex-col items-start gap-3 p-5">
        <p className="text-sm font-medium text-fg">
          Add a system version first
        </p>
        <p className="text-sm text-fg-muted">
          A trace records which system configuration produced the interaction, so
          this project needs at least one system version.
        </p>
        <LinkButton
          variant="secondary"
          href={`/projects/${projectId}/system-versions`}
        >
          Add system version
        </LinkButton>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <p className="text-xs text-fg-subtle">
          Records one interaction using only the fields below. The dashboard
          never captures request headers, cookies, environment variables, or
          credentials — send only data you are permitted to evaluate.
        </p>

        <Select
          label="System version"
          value={systemVersionId}
          onChange={(event) => setSystemVersionId(event.target.value)}
          disabled={create.isPending}
        >
          <option value="">Select…</option>
          {versionList.map((version) => (
            <option key={version.id} value={version.id}>
              {version.name} {version.version} — {version.provider}/{version.model}
            </option>
          ))}
        </Select>

        <TextArea
          label="Input"
          mono
          rows={3}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={create.isPending}
          hint="The prompt / request sent to the system."
        />
        <TextArea
          label="Production output (historical, not ground truth)"
          mono
          rows={3}
          value={output}
          onChange={(event) => setOutput(event.target.value)}
          disabled={create.isPending}
          hint="What the live system actually returned. Optional. Never used as the expected answer."
        />
        <TextArea
          label="Reference output (optional)"
          mono
          rows={2}
          value={reference}
          onChange={(event) => setReference(event.target.value)}
          disabled={create.isPending}
          hint="The known-good answer, if you have one. This is what replayed evaluators compare against."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Latency (ms, optional)"
            type="number"
            min={0}
            step={1}
            value={latency}
            onChange={(event) => setLatency(event.target.value)}
            error={latencyParsed.invalid ? "Number ≥ 0" : undefined}
            disabled={create.isPending}
          />
          <TextField
            label="Cost (USD, optional)"
            type="number"
            min={0}
            step={0.0001}
            value={cost}
            onChange={(event) => setCost(event.target.value)}
            error={costParsed.invalid ? "Number ≥ 0" : undefined}
            disabled={create.isPending}
          />
        </div>

        {create.isError ? (
          <p className="text-sm text-block">
            {apiErrorMessage(create.error, "Could not add the trace.")}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Adding…" : "Add trace"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
