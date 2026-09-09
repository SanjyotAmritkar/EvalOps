"use client";

import { useMemo, useState, type FormEvent } from "react";
import { PlayIcon, PlusIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { TextField } from "@/components/ui/text-field";
import { ApiError } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import {
  EVALUATOR_TYPES,
  OLLAMA_DEFAULT_BASE_URL,
  OLLAMA_DEFAULT_TIMEOUT_SECONDS,
  type AsyncJob,
  type ExecutionBackend,
  type EvaluatorType,
} from "@/lib/api/types";
import { useRunExperimentAsync } from "@/lib/query/experiments";
import {
  buildRunRequest,
  defaultCaseSensitive,
  isRunConfigValid,
  newEvaluatorRow,
  validateRunConfig,
  type RunConfigState,
} from "@/lib/run-config";

const EVALUATOR_HELP: Record<EvaluatorType, string> = {
  exact_match:
    "Passes when the output equals each case's expected output.",
  contains:
    "Passes when the output contains each case's expected output.",
  regex_match: "Passes when the pattern is found in the output (re.search).",
};

export function RunForm({
  experimentId,
  onEnqueued,
  disabled = false,
}: {
  experimentId: string;
  /** Called with the freshly queued job once the 202 lands. */
  onEnqueued: (job: AsyncJob) => void;
  /** True while a job for this experiment is already active. */
  disabled?: boolean;
}) {
  const run = useRunExperimentAsync(experimentId);
  const [state, setState] = useState<RunConfigState>({
    backend: "mock",
    baseUrl: OLLAMA_DEFAULT_BASE_URL,
    timeoutSeconds: String(OLLAMA_DEFAULT_TIMEOUT_SECONDS),
    evaluators: [newEvaluatorRow("contains")],
  });

  const errors = useMemo(() => validateRunConfig(state), [state]);
  const busy = run.isPending || disabled;
  const canRun = isRunConfigValid(errors) && !busy;

  function patchRow(index: number, patch: Partial<RunConfigState["evaluators"][number]>) {
    setState((current) => ({
      ...current,
      evaluators: current.evaluators.map((row, i) =>
        i === index ? { ...row, ...patch } : row,
      ),
    }));
  }

  function changeType(index: number, type: EvaluatorType) {
    setState((current) => ({
      ...current,
      evaluators: current.evaluators.map((row, i) =>
        i === index
          ? {
              ...row,
              type,
              caseSensitive: defaultCaseSensitive(type),
              pattern: type === "regex_match" ? row.pattern : "",
            }
          : row,
      ),
    }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canRun) return;
    run.mutate(buildRunRequest(state), {
      onSuccess: (job) => onEnqueued(job),
    });
  }

  const apiError = run.error instanceof ApiError ? run.error : null;

  return (
    <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
      <fieldset
        className="flex min-w-0 flex-col gap-5 disabled:opacity-60"
        disabled={busy}
      >
        <div className="grid gap-4 sm:grid-cols-[200px_1fr]">
          <Select
            label="Execution backend"
            value={state.backend}
            onChange={(event) =>
              setState((current) => ({
                ...current,
                backend: event.target.value as ExecutionBackend,
              }))
            }
          >
            <option value="mock">mock</option>
            <option value="ollama">ollama</option>
          </Select>
          <p className="self-end pb-2 text-xs text-fg-subtle">
            {state.backend === "mock"
              ? "Deterministic offline simulation — no network."
              : "Real inference against a local Ollama server. Both system versions must use the ollama provider."}
          </p>
        </div>

        {state.backend === "ollama" ? (
          <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
            <TextField
              label="Base URL"
              value={state.baseUrl}
              onChange={(event) =>
                setState((current) => ({
                  ...current,
                  baseUrl: event.target.value,
                }))
              }
              autoComplete="off"
            />
            <TextField
              label="Timeout (seconds)"
              type="number"
              min={1}
              step={1}
              value={state.timeoutSeconds}
              onChange={(event) =>
                setState((current) => ({
                  ...current,
                  timeoutSeconds: event.target.value,
                }))
              }
            />
            {errors.ollama ? (
              <p className="text-xs text-block sm:col-span-2">{errors.ollama}</p>
            ) : null}
          </div>
        ) : null}

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-medium text-fg">Evaluators</legend>
          <p className="text-xs text-fg-subtle">
            At least one. Each is scored per run; its pass-rate becomes a metric
            named after the evaluator.
          </p>

          <div className="flex flex-col gap-3">
            {state.evaluators.map((row, index) => (
              <div
                key={index}
                className="flex flex-col gap-3 rounded-md border border-border p-3"
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select
                    label="Type"
                    value={row.type}
                    onChange={(event) =>
                      changeType(index, event.target.value as EvaluatorType)
                    }
                  >
                    {EVALUATOR_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </Select>
                  <TextField
                    label="Name (optional)"
                    placeholder={row.type}
                    value={row.name}
                    onChange={(event) =>
                      patchRow(index, { name: event.target.value })
                    }
                    autoComplete="off"
                  />
                </div>

                {row.type === "regex_match" ? (
                  <TextField
                    label="Pattern"
                    placeholder="e.g. ^\\s*yes"
                    value={row.pattern}
                    onChange={(event) =>
                      patchRow(index, { pattern: event.target.value })
                    }
                    error={errors.rows[index] ?? undefined}
                    autoComplete="off"
                  />
                ) : (
                  <label className="flex items-center gap-2 text-sm text-fg">
                    <input
                      type="checkbox"
                      checked={row.caseSensitive}
                      onChange={(event) =>
                        patchRow(index, { caseSensitive: event.target.checked })
                      }
                      className="h-4 w-4 rounded border-border accent-accent"
                    />
                    Case sensitive
                  </label>
                )}

                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-fg-subtle">
                    {EVALUATOR_HELP[row.type]}
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      setState((current) => ({
                        ...current,
                        evaluators: current.evaluators.filter(
                          (_, i) => i !== index,
                        ),
                      }))
                    }
                    disabled={state.evaluators.length === 1}
                    className="shrink-0 text-xs font-medium text-fg-subtle transition-colors hover:text-fg disabled:opacity-40"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={() =>
              setState((current) => ({
                ...current,
                evaluators: [...current.evaluators, newEvaluatorRow("contains")],
              }))
            }
            className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-accent transition-colors hover:underline"
          >
            <PlusIcon width={13} height={13} />
            Add evaluator
          </button>

          {errors.evaluators ? (
            <p className="text-xs text-block">{errors.evaluators}</p>
          ) : null}
        </fieldset>
      </fieldset>

      <div className="flex flex-col gap-2">
        <div>
          <Button type="submit" disabled={!canRun}>
            <PlayIcon width={14} height={14} />
            {run.isPending ? "Queuing…" : "Run evaluation"}
          </Button>
        </div>

        {run.isPending ? (
          <p className="text-sm text-fg-muted" role="status">
            Submitting the run to the queue…
          </p>
        ) : null}

        {run.isError ? (
          <p className="text-sm text-block">
            {apiError?.status === 422
              ? `Configuration rejected: ${apiError.message}`
              : apiError?.status === 500
                ? "The run could not be queued — the task broker is unavailable. Try again in a moment."
                : apiErrorMessage(run.error, "The run could not be queued.")}
          </p>
        ) : null}
      </div>
    </form>
  );
}
