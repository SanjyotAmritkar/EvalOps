import type { ReactNode } from "react";

export function DefinitionList({ children }: { children: ReactNode }) {
  return (
    <dl className="flex flex-col divide-y divide-border rounded-lg border border-border">
      {children}
    </dl>
  );
}

export function DefinitionItem({
  term,
  children,
}: {
  term: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:gap-4">
      <dt className="w-44 shrink-0 text-sm text-fg-subtle">{term}</dt>
      <dd className="min-w-0 flex-1 text-sm text-fg">{children}</dd>
    </div>
  );
}
