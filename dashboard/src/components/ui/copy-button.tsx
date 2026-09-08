"use client";

import { useState } from "react";
import { CheckIcon, CopyIcon } from "@/components/icons";
import { cn } from "@/lib/cn";

export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — leave the label unchanged */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs font-medium text-fg-muted",
        "transition-colors hover:bg-surface hover:text-fg",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {copied ? (
        <CheckIcon width={13} height={13} />
      ) : (
        <CopyIcon width={13} height={13} />
      )}
      {copied ? "Copied" : label}
    </button>
  );
}
