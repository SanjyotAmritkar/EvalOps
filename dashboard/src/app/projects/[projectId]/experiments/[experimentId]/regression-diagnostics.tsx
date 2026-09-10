"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/cn";
import type {
  DatasetCase,
  EvaluationRun,
  RegressingCase,
  RegressionDiagnostics,
} from "@/lib/api/types";
import { diagnosticCategory, scoreTransitions } from "@/lib/diagnostics";
import { shortId } from "@/lib/format";
import { RunEvidence } from "./run-evidence";

const INITIAL_VISIBLE = 6;

function TransitionTable({
  baseline,
  candidate,
}: {
  baseline: EvaluationRun | undefined;
  candidate: EvaluationRun | undefined;
}) {
  const rows = scoreTransitions(baseline, candidate).filter(
    (t) => t.baseline || t.candidate,
  );
  if (rows.length === 0) return null;
  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : v.toFixed(3);
  const verdict = (passed: boolean | null | undefined) =>
    passed === null || passed === undefined
      ? "—"
      : passed
        ? "pass"
        : "fail";

  return (
    <table className="w-full text-[12px] tabular-nums">
      <thead>
        <tr className="text-left text-fg-subtle">
          <th className="py-1 pr-3 font-medium">Evaluator</th>
          <th className="py-1 pr-3 font-medium">Baseline</th>
          <th className="py-1 pr-3 font-medium">Candidate</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr
            key={t.evaluator}
            className={cn(
              "border-t border-border",
              t.regressed && "text-block",
            )}
          >
            <td className="py-1 pr-3 font-mono">{t.evaluator}</td>
            <td className="py-1 pr-3">
              {verdict(t.baseline?.passed)} · {fmt(t.baseline?.score)}
            </td>
            <td className="py-1 pr-3">
              {t.regressed ? <span aria-hidden>→ </span> : null}
              {verdict(t.candidate?.passed)} · {fmt(t.candidate?.score)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CaseRow({
  entry,
  runsById,
  datasetCase,
}: {
  entry: RegressingCase;
  runsById: Map<string, EvaluationRun>;
  datasetCase: DatasetCase | undefined;
}) {
  const baseline = runsById.get(entry.representative.baseline_run_id);
  const candidate = runsById.get(entry.representative.candidate_run_id);

  return (
    <details className="rounded-lg border border-border">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2.5 text-[13px]">
        <span className="font-mono text-fg-muted">{shortId(entry.case_id)}</span>
        <span className="text-fg-subtle">
          repeat {entry.representative.repeat_index}
        </span>
        {entry.categories.map((category) => (
          <Badge
            key={category}
            tone={category === "provider_execution_failure" ? "block" : "warn"}
          >
            {diagnosticCategory(category).label}
          </Badge>
        ))}
      </summary>

      <div className="flex flex-col gap-4 border-t border-border px-3 py-3">
        {datasetCase ? (
          <div className="flex flex-col gap-1 text-[13px]">
            <span className="text-fg-subtle">Input</span>
            <p className="whitespace-pre-wrap break-words text-fg-muted">
              {datasetCase.input}
            </p>
            {datasetCase.expected_output ? (
              <>
                <span className="mt-1 text-fg-subtle">Expected output</span>
                <p className="whitespace-pre-wrap break-words text-fg-muted">
                  {datasetCase.expected_output}
                </p>
              </>
            ) : null}
          </div>
        ) : null}

        <div className="overflow-x-auto">
          <TransitionTable baseline={baseline} candidate={candidate} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <span className="text-[12px] font-semibold text-fg-subtle">
              Baseline run
            </span>
            {baseline ? (
              <RunEvidence run={baseline} />
            ) : (
              <p className="text-[12px] text-fg-subtle">Run not found.</p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-[12px] font-semibold text-fg-subtle">
              Candidate run
            </span>
            {candidate ? (
              <RunEvidence run={candidate} />
            ) : (
              <p className="text-[12px] text-fg-subtle">Run not found.</p>
            )}
          </div>
        </div>
      </div>
    </details>
  );
}

/**
 * Deterministic case-level explanation of a BLOCK / regression, from the
 * backend's `GET /diagnostics`. It never states a case is "wrong" beyond what
 * the evaluator evidence shows, and it never affects the release decision — it
 * only groups the regressing cases so a reviewer can inspect them.
 */
export function RegressionDiagnosticsPanel({
  diagnostics,
  runs,
  datasetCases = [],
  blocked,
}: {
  diagnostics: RegressionDiagnostics | undefined;
  runs: EvaluationRun[];
  datasetCases?: DatasetCase[];
  blocked: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!diagnostics || !diagnostics.available) return null;

  const runsById = new Map(runs.map((r) => [r.id, r]));
  const caseById = new Map(datasetCases.map((c) => [c.id, c]));
  const cases = diagnostics.cases;
  const visible = expanded ? cases : cases.slice(0, INITIAL_VISIBLE);

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-fg">
          {blocked ? "Why was this blocked?" : "Regressing cases"}
        </h2>
        <InfoHint label="What is a regressing case?" />
      </div>

      {diagnostics.regressing_pairs === 0 ? (
        <p className="text-[14px] leading-relaxed text-fg-muted">
          No case-level regressions — every candidate run matched or beat its
          baseline across {diagnostics.matched_pairs} paired run
          {diagnostics.matched_pairs === 1 ? "" : "s"}.
        </p>
      ) : (
        <>
          <p className="text-[14px] leading-relaxed text-fg-muted">
            {diagnostics.regressing_cases} regressing case
            {diagnostics.regressing_cases === 1 ? "" : "s"} across{" "}
            {diagnostics.regressing_pairs} paired run
            {diagnostics.regressing_pairs === 1 ? "" : "s"}. Categories are
            derived mechanically from the evidence; they explain the result, they
            do not produce it.
          </p>

          <ul className="flex flex-wrap gap-2">
            {diagnostics.categories.map((c) => {
              const meta = diagnosticCategory(c.category);
              return (
                <li
                  key={c.category}
                  title={meta.description}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[13px]"
                >
                  <span className="font-medium text-fg">{meta.label}</span>
                  <span className="tabular-nums text-fg-subtle">
                    {c.pairs} pair{c.pairs === 1 ? "" : "s"} · {c.cases} case
                    {c.cases === 1 ? "" : "s"}
                  </span>
                </li>
              );
            })}
          </ul>

          {diagnostics.evaluators.length > 0 ? (
            <ul className="flex flex-col gap-0.5 text-[13px] text-fg-subtle">
              {diagnostics.evaluators.map((e) => (
                <li key={e.evaluator}>
                  <span className="font-mono text-fg-muted">{e.evaluator}</span>
                  {": "}
                  {e.pass_to_fail > 0 ? `${e.pass_to_fail} pass→fail` : null}
                  {e.pass_to_fail > 0 && e.score_drop > 0 ? ", " : null}
                  {e.score_drop > 0 ? `${e.score_drop} score drop` : null}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex flex-col gap-2">
            {visible.map((entry) => (
              <CaseRow
                key={entry.case_id}
                entry={entry}
                runsById={runsById}
                datasetCase={caseById.get(entry.case_id)}
              />
            ))}
          </div>

          {cases.length > INITIAL_VISIBLE ? (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="self-start text-[13px] font-medium text-accent hover:underline"
            >
              {expanded
                ? "Show fewer cases"
                : `Show all ${cases.length} regressing cases`}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}
