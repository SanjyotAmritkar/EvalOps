"use client";

import { useState } from "react";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { LoadingState } from "@/components/feedback/loading-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { apiErrorMessage } from "@/lib/api/errors";
import {
  useJudgeCalibration,
  useJudgeCalibrations,
} from "@/lib/query/judge-calibrations";
import {
  CalibrationResult,
  CalibrationSummaryRow,
} from "./calibration-result";
import { JudgeCalibrationForm } from "./judge-calibration-form";

export default function JudgeCalibrationsPage() {
  const calibrations = useJudgeCalibrations();
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = useJudgeCalibration(selectedId);
  const list = calibrations.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Judge Calibration"
        description="Run a configured LLM judge over human-labeled examples to measure how often it agrees with the humans."
        actions={
          <Button
            variant={showForm ? "secondary" : "primary"}
            onClick={() => setShowForm((value) => !value)}
          >
            {showForm ? "Close" : "New calibration"}
          </Button>
        }
      />

      <p className="rounded-md border border-border bg-surface-raised px-4 py-3 text-[14px] leading-relaxed text-fg-muted">
        Calibration measures judge trustworthiness only. It{" "}
        <span className="font-medium text-fg">
          does not affect release gating
        </span>{" "}
        — a low agreement rate never blocks a release or disables the judge.
        Calibrations are global, not scoped to this project. The judge&rsquo;s API
        key is read from the server environment and is never sent from or shown in
        the dashboard.
      </p>

      {showForm ? (
        <JudgeCalibrationForm
          onCreated={(id) => {
            setSelectedId(id);
            setShowForm(false);
          }}
        />
      ) : null}

      {selectedId ? (
        selected.isPending ? (
          <LoadingState rows={4} />
        ) : selected.isError || !selected.data ? (
          <ErrorState
            title="Could not load that calibration"
            message={apiErrorMessage(selected.error, "The API did not respond.")}
            onRetry={() => void selected.refetch()}
          />
        ) : (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="w-fit text-sm text-accent transition-colors hover:underline"
            >
              ← Back to all calibrations
            </button>
            <CalibrationResult calibration={selected.data} />
          </div>
        )
      ) : calibrations.isPending ? (
        <LoadingState />
      ) : calibrations.isError ? (
        <ErrorState
          title="Could not load calibrations"
          message={apiErrorMessage(
            calibrations.error,
            "The API did not respond.",
          )}
          onRetry={() => void calibrations.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No calibrations yet"
          description="Run a judge over a few pass/fail examples to see how well it agrees with human labels."
          action={
            !showForm ? (
              <Button onClick={() => setShowForm(true)}>New calibration</Button>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          <span className="text-[13px] font-medium text-fg-subtle">
            Persisted calibrations
          </span>
          {list.map((calibration) => (
            <CalibrationSummaryRow
              key={calibration.id}
              calibration={calibration}
              selected={false}
              onSelect={() => setSelectedId(calibration.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
