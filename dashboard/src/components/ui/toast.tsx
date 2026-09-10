"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { cn } from "@/lib/cn";

type ToastTone = "success" | "error" | "info";

interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

interface ToastApi {
  toast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const AUTO_DISMISS_MS = 4500;

const TONE_CLASS: Record<ToastTone, string> = {
  success: "border-pass/40 text-pass",
  error: "border-block/40 text-block",
  info: "border-accent/40 text-accent",
};

/**
 * Transient action feedback only ("Project created", "Copied"). Not for
 * persistent state (PASS/BLOCK), job progress, or field validation.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start justify-between gap-3 rounded-md border bg-surface px-4 py-3 text-[14px] shadow-lg",
              TONE_CLASS[t.tone],
            )}
          >
            <span className="text-fg">{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="shrink-0 text-fg-subtle transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden>
                <path
                  d="M6 6l12 12M18 6L6 18"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Returns `{ toast }`. Safe to call outside a provider — becomes a no-op. */
export function useToast(): ToastApi {
  return useContext(ToastContext) ?? { toast: () => {} };
}
