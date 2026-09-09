import { cn } from "@/lib/cn";

/** Marks a system version as the baseline (reference) or candidate (change
 * under test). Neutral vs accent — not a PASS/BLOCK signal. */
export function RoleChip({
  role,
  className,
}: {
  role: "baseline" | "candidate";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        role === "baseline"
          ? "bg-surface-raised text-fg-muted"
          : "bg-accent/10 text-accent",
        className,
      )}
    >
      {role}
    </span>
  );
}
