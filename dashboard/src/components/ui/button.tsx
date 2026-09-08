import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";

const BASE =
  "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 text-sm font-medium " +
  "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-canvas " +
  "disabled:pointer-events-none disabled:opacity-50";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent/90",
  secondary: "border border-border bg-surface text-fg hover:bg-surface-raised",
  ghost: "text-fg-muted hover:bg-surface-raised hover:text-fg",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(BASE, VARIANTS[variant], className)}
      {...props}
    />
  );
}

type LinkButtonProps = ComponentProps<typeof Link> & { variant?: Variant };

/** A Next.js `Link` styled as a button. */
export function LinkButton({
  variant = "primary",
  className,
  ...props
}: LinkButtonProps) {
  return (
    <Link className={cn(BASE, VARIANTS[variant], className)} {...props} />
  );
}
