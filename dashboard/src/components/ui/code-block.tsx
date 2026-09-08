import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { CopyButton } from "./copy-button";

/** Monospace block for prompt templates and JSON config, with an optional
 * header label and copy affordance. Not a syntax highlighter — just readable. */
export function CodeBlock({
  children,
  label,
  copyValue,
  wrap = true,
  className,
}: {
  children: ReactNode;
  label?: string;
  copyValue?: string;
  wrap?: boolean;
  className?: string;
}) {
  const hasHeader = label !== undefined || copyValue !== undefined;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border bg-surface-raised",
        className,
      )}
    >
      {hasHeader ? (
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
          <span className="font-mono text-xs text-fg-subtle">{label}</span>
          {copyValue !== undefined ? <CopyButton value={copyValue} /> : null}
        </div>
      ) : null}
      <pre
        className={cn(
          "overflow-x-auto px-3 py-2.5 font-mono text-[13px] leading-relaxed text-fg",
          wrap && "whitespace-pre-wrap break-words",
        )}
      >
        {children}
      </pre>
    </div>
  );
}
