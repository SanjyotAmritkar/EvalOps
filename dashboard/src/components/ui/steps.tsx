import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface Step {
  title: string;
  description: ReactNode;
  /** Optional trailing status marker (e.g. done / to-do). */
  done?: boolean;
}

/**
 * A numbered, vertically-stacked explanation of a real workflow. Not a chart
 * and not decorative — used for "How EvalOps works" and project readiness.
 */
export function Steps({
  steps,
  showStatus = false,
  className,
}: {
  steps: readonly Step[];
  showStatus?: boolean;
  className?: string;
}) {
  return (
    <ol className={cn("flex flex-col", className)}>
      {steps.map((step, index) => (
        <li key={index} className="flex gap-4 pb-5 last:pb-0">
          <div className="flex flex-col items-center">
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[13px] font-semibold",
                showStatus && step.done
                  ? "border-pass/40 bg-pass/10 text-pass"
                  : "border-border bg-surface text-fg-muted",
              )}
              aria-hidden
            >
              {showStatus && step.done ? "✓" : index + 1}
            </span>
            {index < steps.length - 1 ? (
              <span className="mt-1 w-px flex-1 bg-border" aria-hidden />
            ) : null}
          </div>
          <div className="flex flex-col gap-0.5 pt-0.5">
            <p className="text-[15px] font-medium text-fg">{step.title}</p>
            <div className="text-[14px] leading-relaxed text-fg-muted">
              {step.description}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
