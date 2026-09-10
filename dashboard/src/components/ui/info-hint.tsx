"use client";

import { useHelp } from "@/components/help/help-provider";
import { QuestionIcon } from "@/components/icons";

/**
 * A small "?" affordance next to a term. It opens the global Help drawer
 * (CP 10.1) rather than showing its own popover — one accessible surface for
 * every explanation, no tooltip soup. `label` names the concept for screen
 * readers, e.g. "What is a regressing case?".
 */
export function InfoHint({ label }: { label: string }) {
  const { openHelp } = useHelp();
  return (
    <button
      type="button"
      onClick={openHelp}
      aria-label={label}
      title={label}
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border text-fg-subtle transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <QuestionIcon width={10} height={10} />
      <span className="sr-only">{label}</span>
    </button>
  );
}
