"use client";

import { Badge } from "@/components/ui/badge";
import type { EvaluationRun } from "@/lib/api/types";

/** Compact renderer for one JSON-ish value — an object/array shows as a small
 * pretty block, a scalar inline. Never a raw unreadable dump. */
function JsonValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-fg-subtle">—</span>;
  }
  if (typeof value === "object") {
    return (
      <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-surface-raised px-2 py-1 font-mono text-[11px] text-fg-muted">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return (
    <code className="font-mono text-[12px] text-fg-muted">{String(value)}</code>
  );
}

/**
 * Per-run evidence: evaluator scores plus, when the external system reported
 * them, the retrieved context (CP 9.1) and the tool trajectory (CP 9.2).
 * Text-only runs show only their scores — no empty RAG/agent sections.
 *
 * This is evidence *about* an execution: retrieved context is not evaluation
 * ground truth, and the tool trajectory alone does not prove the task was
 * solved correctly.
 */
export function RunEvidence({ run }: { run: EvaluationRun }) {
  const retrieval = run.retrieval ?? [];
  const toolCalls = run.tool_calls ?? [];
  const scores = run.scores ?? [];
  const hasRetrieval = retrieval.length > 0;
  const hasTools = toolCalls.length > 0;

  return (
    <div className="flex flex-col gap-4 border-l-2 border-border pl-3">
      {run.error !== null ? (
        <p className="text-xs text-block">Provider error: {run.error}</p>
      ) : (
        <section className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
            Evaluator scores
          </span>
          {scores.length === 0 ? (
            <p className="text-xs text-fg-subtle">No scores recorded.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {scores.map((score) => (
                <li
                  key={score.evaluator}
                  className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-0.5 text-[12px]"
                >
                  <span className="font-mono text-fg-muted">
                    {score.evaluator}
                  </span>
                  <span className="tabular-nums text-fg">
                    {score.score.toFixed(3)}
                  </span>
                  {score.passed === null ? null : (
                    <Badge tone={score.passed ? "pass" : "block"}>
                      {score.passed ? "pass" : "fail"}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {hasRetrieval ? (
        <section className="flex flex-col gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              Retrieved context
            </span>
            <span className="text-[11px] text-fg-subtle">
              What the system reported retrieving — not evaluation ground truth.
            </span>
          </div>
          <ol className="flex flex-col gap-1.5">
            {retrieval.map((item) => (
              <li
                key={`${item.rank}-${item.doc_id}`}
                className="flex flex-col gap-1 rounded-md border border-border p-2"
              >
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12px]">
                  <span className="tabular-nums text-fg-subtle">
                    #{item.rank}
                  </span>
                  <span className="font-mono font-medium text-fg">
                    {item.doc_id}
                  </span>
                  {item.score !== null ? (
                    <span className="tabular-nums text-fg-subtle">
                      score {item.score.toFixed(3)}
                    </span>
                  ) : null}
                </div>
                {item.content ? (
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] text-fg-muted">
                    {item.content}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {hasTools ? (
        <section className="flex flex-col gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-fg-subtle">
              Tool trajectory
            </span>
            <span className="text-[11px] text-fg-subtle">
              The tools the system reported calling, in order. This does not by
              itself prove the task was solved correctly.
            </span>
          </div>
          <ol className="flex flex-col gap-1.5">
            {toolCalls.map((call, index) => (
              <li
                key={index}
                className="flex flex-col gap-1 rounded-md border border-border p-2 text-[12px]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="tabular-nums text-fg-subtle">
                    {index + 1}.
                  </span>
                  <span className="font-mono font-medium text-fg">
                    {call.name}
                  </span>
                  <Badge tone={call.ok ? "pass" : "block"}>
                    {call.ok ? "ok" : "failed"}
                  </Badge>
                </div>
                <div className="grid gap-1 sm:grid-cols-[80px_1fr]">
                  <span className="text-fg-subtle">arguments</span>
                  <JsonValue value={call.arguments} />
                </div>
                {call.result !== null && call.result !== undefined ? (
                  <div className="grid gap-1 sm:grid-cols-[80px_1fr]">
                    <span className="text-fg-subtle">result</span>
                    <JsonValue value={call.result} />
                  </div>
                ) : null}
                {call.error !== null ? (
                  <div className="grid gap-1 sm:grid-cols-[80px_1fr]">
                    <span className="text-fg-subtle">error</span>
                    <span className="text-block">{call.error}</span>
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
