"use client";

import { useHelp } from "@/components/help/help-provider";
import { QuestionIcon } from "@/components/icons";

/**
 * A small "?" affordance next to a term. It opens the global Help drawer
 * (CP 10.1) rather than showing its own popover — one accessible surface for
 * every explanation, no tooltip soup. `label` names the concept for screen
 * readers, e.g. "What is a regressing case?". `term` (a glossary entry id —
 * see `help-provider.tsx`'s `GLOSSARY`) scrolls straight to and focuses the
 * matching entry instead of leaving the reader at the top of the whole list;
 * omit it to open the drawer at the top.
 */
export function InfoHint({ label, term }: { label: string; term?: string }) {
  const { openHelp } = useHelp();
  return (
    <button
      type="button"
      onClick={() => openHelp(term)}
      aria-label={label}
      title={label}
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border text-fg-subtle transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <QuestionIcon width={10} height={10} />
      <span className="sr-only">{label}</span>
    </button>
  );
}
