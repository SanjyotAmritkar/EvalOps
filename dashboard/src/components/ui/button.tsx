import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentProps } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium " +
  "transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-canvas " +
  "disabled:pointer-events-none disabled:opacity-50";

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-[15px]",
  lg: "h-11 px-5 text-base",
};

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent/90 shadow-sm",
  secondary: "border border-border bg-surface text-fg hover:bg-surface-raised",
  ghost: "text-fg-muted hover:bg-surface-raised hover:text-fg",
  danger: "border border-block/40 bg-surface text-block hover:bg-block/10",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(BASE, SIZES[size], VARIANTS[variant], className)}
      {...props}
    />
  );
}

type LinkButtonProps = ComponentProps<typeof Link> & {
  variant?: Variant;
  size?: Size;
};

/** A Next.js `Link` styled as a button. */
export function LinkButton({
  variant = "primary",
  size = "md",
  className,
  ...props
}: LinkButtonProps) {
  return (
    <Link
      className={cn(BASE, SIZES[size], VARIANTS[variant], className)}
      {...props}
    />
  );
}
