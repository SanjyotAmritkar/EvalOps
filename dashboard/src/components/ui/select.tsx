"use client";

import { useId, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function Select({
  label,
  hint,
  error,
  className,
  id,
  children,
  ...props
}: SelectProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-[14px] font-medium text-fg">
        {label}
      </label>
      <select
        id={fieldId}
        aria-invalid={error ? true : undefined}
        className={cn(
          "h-10 rounded-md border border-border bg-surface px-3 text-[15px] text-fg",
          "transition-colors duration-150 focus-visible:outline-none",
          "focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          error && "border-block focus-visible:ring-block",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      {hint && !error ? (
        <p className="text-[13px] text-fg-subtle">{hint}</p>
      ) : null}
      {error ? <p className="text-[13px] text-block">{error}</p> : null}
    </div>
  );
}
