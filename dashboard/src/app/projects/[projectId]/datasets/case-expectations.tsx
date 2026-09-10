"use client";

import type { DatasetCase } from "@/lib/api/types";

/**
 * The RAG / agent ground truth authored on a dataset case (CP 9.1 / 9.2),
 * shown behind progressive disclosure so plain text cases stay uncluttered.
 * Display only — never treated as retrieval evidence or proof of correctness.
 */
export function CaseExpectations({ testCase }: { testCase: DatasetCase }) {
  const ids = testCase.expected_retrieval_ids ?? [];
  const tools = testCase.expected_tool_calls ?? [];
  if (ids.length === 0 && tools.length === 0) return null;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-raised p-3">
      {ids.length > 0 ? (
        <details open>
          <summary className="cursor-pointer text-[13px] font-medium text-fg">
            Retrieval expectations{" "}
            <span className="text-fg-subtle">
              · {ids.length} relevant id{ids.length === 1 ? "" : "s"}
            </span>
          </summary>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {ids.map((id) => (
              <li
                key={id}
                className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-fg-muted"
              >
                {id}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {tools.length > 0 ? (
        <details open>
          <summary className="cursor-pointer text-[13px] font-medium text-fg">
            Tool expectations{" "}
            <span className="text-fg-subtle">
              · {tools.length} call{tools.length === 1 ? "" : "s"}, in order
            </span>
          </summary>
          <ol className="mt-1.5 flex flex-col gap-1.5">
            {tools.map((call, index) => (
              <li
                key={index}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[12px]"
              >
                <span className="font-mono text-fg-subtle">{index + 1}.</span>
                <span className="font-mono font-medium text-fg">
                  {call.name}
                </span>
                {call.arguments === null ? (
                  <span className="text-fg-subtle">(name only)</span>
                ) : (
                  <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
                    {JSON.stringify(call.arguments)}
                  </code>
                )}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </div>
  );
}
