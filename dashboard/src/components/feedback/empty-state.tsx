import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-surface px-6 py-14 text-center">
      <p className="text-lg font-semibold text-fg">{title}</p>
      {description ? (
        <p className="max-w-md text-[15px] leading-relaxed text-fg-muted">
          {description}
        </p>
      ) : null}
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
