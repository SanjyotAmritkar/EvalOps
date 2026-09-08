import Link from "next/link";
import { ArrowLeftIcon } from "@/components/icons";

export function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
    >
      <ArrowLeftIcon width={14} height={14} />
      {label}
    </Link>
  );
}
