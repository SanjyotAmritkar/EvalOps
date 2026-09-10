import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "pass" | "block" | "warn" | "info";

const TONES: Record<Tone, string> = {
  neutral: "border-border text-fg-muted",
  pass: "border-pass/30 text-pass",
  block: "border-block/30 text-block",
  warn: "border-warn/30 text-warn",
  info: "border-accent/30 text-accent",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
