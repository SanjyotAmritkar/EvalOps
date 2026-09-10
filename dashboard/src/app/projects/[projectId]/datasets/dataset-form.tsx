"use client";

import { useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextField } from "@/components/ui/text-field";
import { TextArea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import { parseCasesJsonl } from "@/lib/jsonl";
import { useCreateDataset } from "@/lib/query/datasets";
import { useToast } from "@/components/ui/toast";

const EXAMPLE_TEXT = `{"input": "What is 2 + 2?", "expected_output": "4"}
{"input": "Capital of France?", "expected_output": "Paris"}`;

const EXAMPLE_RAG = `{"input": "reset my password", "expected_output": "Use the reset link", "expected_retrieval_ids": ["kb-42", "kb-43"]}
{"input": "refund policy", "expected_retrieval_ids": ["policy-7"]}`;

const EXAMPLE_AGENT = `{"input": "book a flight to Paris", "expected_tool_calls": [{"name": "search_flights", "arguments": {"dest": "PAR"}}, {"name": "book"}]}
{"input": "what's the weather", "expected_tool_calls": [{"name": "get_weather"}]}`;

export function DatasetForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const create = useCreateDataset(projectId);
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1");
  const [jsonl, setJsonl] = useState("");

  const parsed = useMemo(() => parseCasesJsonl(jsonl), [jsonl]);
  const firstError = parsed.errors[0];

  const versionNumber = Number.parseInt(version, 10);
  const versionValid = Number.isInteger(versionNumber) && versionNumber >= 1;

  const canSubmit =
    name.trim().length > 0 &&
    versionValid &&
    parsed.cases.length > 0 &&
    parsed.errors.length === 0 &&
    !create.isPending;

  const isConflict =
    create.error instanceof ApiError && create.error.status === 409;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      { name: name.trim(), version: versionNumber, cases: parsed.cases },
      {
        onSuccess: () => {
          toast("Dataset created");
          setName("");
          setVersion("1");
          setJsonl("");
          onCreated();
        },
      },
    );
  }

  return (
    <Card className="p-4">
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <div className="grid gap-4 sm:grid-cols-[1fr_150px]">
          <TextField
            label="Name"
            placeholder="e.g. support-golden"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            disabled={create.isPending}
          />
          <TextField
            label="Version"
            type="number"
            min={1}
            step={1}
            value={version}
            onChange={(event) => setVersion(event.target.value)}
            error={
              version !== "" && !versionValid
                ? "Whole number ≥ 1"
                : undefined
            }
            disabled={create.isPending}
          />
        </div>

        <TextArea
          label="Cases (JSONL)"
          mono
          rows={8}
          placeholder={EXAMPLE_TEXT}
          value={jsonl}
          onChange={(event) => setJsonl(event.target.value)}
          disabled={create.isPending}
          hint={
            'One JSON object per line. "input" is required. Optional, add only where relevant: "expected_output" (reference answer) · "expected_retrieval_ids": [string] (RAG relevant chunks) · "expected_tool_calls": [{ "name", "arguments"? }] (agent trajectory) · "origin" / "source_trace_id".'
          }
          error={
            firstError
              ? `Line ${firstError.line}: ${firstError.message}`
              : undefined
          }
        />

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-subtle">
          <span className="font-medium text-fg-subtle">Insert example:</span>
          <button
            type="button"
            className="text-accent transition-colors hover:underline"
            onClick={() => setJsonl(EXAMPLE_TEXT)}
          >
            text-only
          </button>
          <button
            type="button"
            className="text-accent transition-colors hover:underline"
            onClick={() => setJsonl(EXAMPLE_RAG)}
          >
            RAG (retrieval)
          </button>
          <button
            type="button"
            className="text-accent transition-colors hover:underline"
            onClick={() => setJsonl(EXAMPLE_AGENT)}
          >
            agent (tools)
          </button>
          <span>
            {parsed.cases.length} case
            {parsed.cases.length === 1 ? "" : "s"} parsed
            {parsed.errors.length > 0
              ? ` · ${parsed.errors.length} line${parsed.errors.length === 1 ? "" : "s"} with errors`
              : ""}
          </span>
        </div>

        {create.isError ? (
          <p className="text-sm text-block">
            {isConflict
              ? `A dataset named “${name.trim()}” at version ${versionNumber} already exists in this project.`
              : apiErrorMessage(create.error, "Could not create the dataset.")}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Creating…" : "Create dataset"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
