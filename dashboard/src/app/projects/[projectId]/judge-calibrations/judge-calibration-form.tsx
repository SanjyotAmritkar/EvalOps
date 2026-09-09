"use client";

import { useMemo, useState, type FormEvent } from "react";
import { PlusIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { TextArea } from "@/components/ui/textarea";
import { TextField } from "@/components/ui/text-field";
import { apiErrorMessage } from "@/lib/api/errors";
import { PROVIDER_NAMES, type ProviderName } from "@/lib/api/types";
import { useCreateJudgeCalibration } from "@/lib/query/judge-calibrations";

interface ExampleRow {
  input: string;
  output: string;
  reference: string;
  humanPass: boolean;
}

const emptyRow: ExampleRow = {
  input: "",
  output: "",
  reference: "",
  humanPass: true,
};

export function JudgeCalibrationForm({
  onCreated,
}: {
  onCreated: (calibrationId: string) => void;
}) {
  const create = useCreateJudgeCalibration();
  const [provider, setProvider] = useState<ProviderName>("openai");
  const [model, setModel] = useState("");
  const [name, setName] = useState("");
  const [temperature, setTemperature] = useState("0");
  const [rows, setRows] = useState<ExampleRow[]>([
    { ...emptyRow },
    { ...emptyRow },
    { ...emptyRow },
  ]);

  const temperatureNumber = Number(temperature);
  const temperatureValid =
    temperature.trim() !== "" &&
    Number.isFinite(temperatureNumber) &&
    temperatureNumber >= 0;

  const rowErrors = useMemo(
    () =>
      rows.map((row) =>
        row.input.trim() === "" || row.output.trim() === ""
          ? "input and system output are required"
          : null,
      ),
    [rows],
  );

  const canSubmit =
    model.trim() !== "" &&
    temperatureValid &&
    rows.length >= 1 &&
    rowErrors.every((error) => error === null) &&
    !create.isPending;

  function updateRow(index: number, patch: Partial<ExampleRow>) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      {
        provider,
        model: model.trim(),
        ...(name.trim() !== "" ? { name: name.trim() } : {}),
        temperature: temperatureNumber,
        examples: rows.map((row) => ({
          input: row.input,
          output: row.output,
          human_pass: row.humanPass,
          ...(row.reference.trim() !== ""
            ? { reference: row.reference.trim() }
            : {}),
        })),
      },
      { onSuccess: (calibration) => onCreated(calibration.id) },
    );
  }

  return (
    <Card className="p-4">
      <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
        <fieldset
          className="flex min-w-0 flex-col gap-4 disabled:opacity-60"
          disabled={create.isPending}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Judge provider"
              value={provider}
              onChange={(event) =>
                setProvider(event.target.value as ProviderName)
              }
            >
              {PROVIDER_NAMES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
            <TextField
              label="Judge model"
              placeholder="e.g. gpt-4o-mini"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              autoComplete="off"
            />
            <TextField
              label="Name (optional)"
              placeholder="llm_judge"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
            />
            <TextField
              label="Temperature"
              type="number"
              min={0}
              step={0.1}
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
              error={!temperatureValid ? "Number ≥ 0" : undefined}
            />
          </div>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-sm font-medium text-fg">
              Human-labeled examples
            </legend>
            <p className="text-xs text-fg-subtle">
              3–5 is plenty. Give each a clear pass/fail human verdict. The judge
              runs once per example; a judge call that fails is recorded and
              excluded from the metrics.
            </p>

            <div className="flex flex-col gap-4">
              {rows.map((row, index) => (
                <div
                  key={index}
                  className="flex flex-col gap-3 rounded-md border border-border p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-fg-subtle">
                      Example {index + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setRows((current) =>
                          current.length === 1
                            ? current
                            : current.filter((_, i) => i !== index),
                        )
                      }
                      disabled={rows.length === 1}
                      className="text-xs font-medium text-fg-subtle transition-colors hover:text-fg disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </div>
                  <TextArea
                    label={`Example ${index + 1} input`}
                    className="min-h-16"
                    value={row.input}
                    onChange={(event) =>
                      updateRow(index, { input: event.target.value })
                    }
                  />
                  <TextArea
                    label={`Example ${index + 1} system output`}
                    className="min-h-16"
                    value={row.output}
                    onChange={(event) =>
                      updateRow(index, { output: event.target.value })
                    }
                  />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField
                      label={`Example ${index + 1} reference (optional)`}
                      value={row.reference}
                      onChange={(event) =>
                        updateRow(index, { reference: event.target.value })
                      }
                      autoComplete="off"
                    />
                    <Select
                      label={`Example ${index + 1} human verdict`}
                      value={row.humanPass ? "pass" : "fail"}
                      onChange={(event) =>
                        updateRow(index, {
                          humanPass: event.target.value === "pass",
                        })
                      }
                    >
                      <option value="pass">Pass</option>
                      <option value="fail">Fail</option>
                    </Select>
                  </div>
                  {rowErrors[index] ? (
                    <p className="text-xs text-block">{rowErrors[index]}</p>
                  ) : null}
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={() =>
                setRows((current) => [...current, { ...emptyRow }])
              }
              className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-accent transition-colors hover:underline"
            >
              <PlusIcon width={13} height={13} />
              Add example
            </button>
          </fieldset>
        </fieldset>

        {create.isError ? (
          <p className="text-sm text-block">
            {apiErrorMessage(
              create.error,
              "Could not run the calibration. Check the judge provider's API key is set in the server environment.",
            )}
          </p>
        ) : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {create.isPending ? "Running judge…" : "Run calibration"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
