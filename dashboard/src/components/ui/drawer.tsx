"use client";

import {
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { cn } from "@/lib/cn";

/**
 * A minimal accessible slide-over. No dependency, no portal — rendered in place
 * with a fixed overlay. Escape and backdrop click close it; focus moves into
 * the panel on open and returns to the trigger on close.
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    panel?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      restoreRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          "relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-border bg-surface shadow-xl outline-none",
          className,
        )}
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-border bg-surface px-5 py-4">
          <h2 className="text-lg font-semibold text-fg">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-fg-muted transition-colors hover:bg-surface-raised hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
              <path
                d="M6 6l12 12M18 6L6 18"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
        <div className="flex-1 px-5 py-5">{children}</div>
      </div>
    </div>
  );
}
