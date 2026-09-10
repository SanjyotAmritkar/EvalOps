"use client";

import { useId, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
  mono?: boolean;
}

export function TextArea({
  label,
  hint,
  error,
  mono,
  className,
  id,
  ...props
}: TextAreaProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const describedBy = error
    ? `${fieldId}-error`
    : hint
      ? `${fieldId}-hint`
      : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-[14px] font-medium text-fg">
        {label}
      </label>
      <textarea
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          "min-h-24 rounded-md border border-border bg-surface px-3 py-2 text-[15px] text-fg",
          "placeholder:text-fg-subtle",
          "transition-colors duration-150 focus-visible:outline-none",
          "focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          mono && "font-mono text-[13px] leading-relaxed",
          error && "border-block focus-visible:ring-block",
          className,
        )}
        {...props}
      />
      {hint && !error ? (
        <p id={`${fieldId}-hint`} className="text-[13px] text-fg-subtle">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${fieldId}-error`} className="text-[13px] text-block">
          {error}
        </p>
      ) : null}
    </div>
  );
}
