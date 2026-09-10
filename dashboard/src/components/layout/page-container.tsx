import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const WIDTH = {
  default: "max-w-5xl",
  wide: "max-w-7xl",
} as const;

export function PageContainer({
  children,
  className,
  size = "default",
}: {
  children: ReactNode;
  className?: string;
  size?: keyof typeof WIDTH;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-6 py-10 sm:px-8",
        WIDTH[size],
        className,
      )}
    >
      {children}
    </div>
  );
}
