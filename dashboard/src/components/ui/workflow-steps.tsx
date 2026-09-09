import { Fragment } from "react";
import { cn } from "@/lib/cn";

export interface WorkflowStep {
  label: string;
  tone?: "neutral" | "candidate";
}

/**
 * Compact, restrained visual of the EvalOps workflow: tinted step chips joined
 * by arrows. No icons, no animation.
 */
export function WorkflowSteps({
  steps,
  className,
}: {
  steps: readonly WorkflowStep[];
  className?: string;
}) {
  return (
    <ol
      aria-label="Workflow"
      className={cn("flex flex-wrap items-center gap-x-2 gap-y-2", className)}
    >
      {steps.map((step, index) => (
        <Fragment key={step.label}>
          {index > 0 ? (
            <span aria-hidden className="text-fg-subtle">
              →
            </span>
          ) : null}
          <li
            className={cn(
              "rounded-md px-2.5 py-1 text-[13px] font-medium",
              step.tone === "candidate"
                ? "bg-accent/10 text-accent"
                : "bg-surface-raised text-fg",
            )}
          >
            {step.label}
          </li>
        </Fragment>
      ))}
    </ol>
  );
}
