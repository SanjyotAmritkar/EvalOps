"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { TextField } from "@/components/ui/text-field";
import { TextArea } from "@/components/ui/textarea";
import { apiErrorMessage } from "@/lib/api/errors";
import { PROVIDER_NAMES, type ProviderName } from "@/lib/api/types";
import { parseJsonObject } from "@/lib/json";
import { useCreateSystemVersion } from "@/lib/query/system-versions";

export function SystemVersionForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const create = useCreateSystemVersion(projectId);

  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [provider, setProvider] = useState<ProviderName>("openai");
  const [model, setModel] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [parameters, setParameters] = useState("");
  const [ragConfig, setRagConfig] = useState("");
  const [toolPolicy, setToolPolicy] = useState("");

  const parametersParsed = parseJsonObject(parameters);
  const ragParsed = parseJsonObject(ragConfig);
  const toolParsed = parseJsonObject(toolPolicy);
  const jsonValid =
    !parametersParsed.error && !ragParsed.error && !toolParsed.error;

  const canSubmit =
    name.trim().length > 0 &&
    version.trim().length > 0 &&
    model.trim().length > 0 &&
    promptTemplate.trim().length > 0 &&
    jsonValid &&
    !create.isPending;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      {
        name: name.trim(),
        version: version.trim(),
        provider,
        model: model.trim(),
        prompt_template: promptTemplate,
        parameters: parametersParsed.value ?? {},
        rag_config: ragParsed.value,
        tool_policy: toolParsed.value,
      },
      {
        onSuccess: () => {
          setName("");
          setVersion("");
          setModel("");
          setPromptTemplate("");
          setParameters("");
          setRagConfig("");
          setToolPolicy("");
          onCreated();
        },
      },
    );
  }

  return (
    <Card className="p-4">
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Name"
            placeholder="e.g. support-prompt"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            disabled={create.isPending}
          />
          <TextField
            label="Version"
            placeholder="e.g. v1"
            value={version}
            onChange={(event) => setVersion(event.target.value)}
            autoComplete="off"
            disabled={create.isPending}
          />
          <Select
            label="Provider"
            value={provider}
            onChange={(event) =>
              setProvider(event.target.value as ProviderName)
            }
            disabled={create.isPending}
          >
            {PROVIDER_NAMES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
          <TextField
            label="Model"
            placeholder="e.g. gpt-4o-mini, llama3.2"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            autoComplete="off"
            disabled={create.isPending}
          />
        </div>

        <TextArea
          label="Prompt template"
          mono
          rows={5}
          placeholder="Q: ${input}"
          value={promptTemplate}
          onChange={(event) => setPromptTemplate(event.target.value)}
          disabled={create.isPending}
          hint="The case input is substituted wherever ${input} appears."
        />

        <TextArea
          label="Parameters (JSON object, optional)"
          mono
          rows={3}
          placeholder='{ "temperature": 0 }'
          value={parameters}
          onChange={(event) => setParameters(event.target.value)}
          disabled={create.isPending}
          error={parametersParsed.error ?? undefined}
        />

        <details className="rounded-md border border-border">
          <summary className="cursor-pointer px-3 py-2 text-sm text-fg-muted">
            RAG config / tool policy (optional)
          </summary>
          <div className="flex flex-col gap-4 border-t border-border p-3">
            <TextArea
              label="rag_config (JSON object)"
              mono
              rows={3}
              value={ragConfig}
              onChange={(event) => setRagConfig(event.target.value)}
              disabled={create.isPending}
              error={ragParsed.error ?? undefined}
            />
            <TextArea
              label="tool_policy (JSON object)"
              mono
              rows={3}
              value={toolPolicy}
              onChange={(event) => setToolPolicy(event.target.value)}
              disabled={create.isPending}
              error={toolParsed.error ?? undefined}
            />
          </div>
        </details>

        {create.isError ? (
          <p className="text-sm text-block">
            {apiErrorMessage(
              create.error,
              "Could not create the system version.",
            )}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Creating…" : "Create system version"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
