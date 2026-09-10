import type {
  HTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { cn } from "@/lib/cn";

/** Scroll-contained bordered table. Compose with THead/TBody/TR/TH/TD. */
export function Table({
  className,
  ...props
}: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table
        className={cn("w-full border-collapse text-[14px]", className)}
        {...props}
      />
    </div>
  );
}

export function THead(props: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className="bg-surface-raised text-left text-[13px] font-medium text-fg-muted"
      {...props}
    />
  );
}

export function TBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />;
}

export function TR({
  className,
  ...props
}: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("border-t border-border first:border-t-0", className)}
      {...props}
    />
  );
}

export function TH({
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn("px-3 py-2.5 font-medium", className)}
      {...props}
    />
  );
}

export function TD({
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-3 py-2.5 align-top text-fg", className)} {...props} />
  );
}
