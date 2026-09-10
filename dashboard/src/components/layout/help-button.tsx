"use client";

import { QuestionIcon } from "@/components/icons";
import { useHelp } from "@/components/help/help-provider";

export function HelpButton() {
  const { openHelp } = useHelp();
  return (
    <button
      type="button"
      onClick={openHelp}
      aria-label="Help"
      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[13px] font-medium text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <QuestionIcon width={15} height={15} />
      Help
    </button>
  );
}
