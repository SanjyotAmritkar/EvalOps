import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";

export function TopBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link
          href="/projects"
          className="flex items-center gap-2 text-sm font-semibold tracking-tight text-fg"
        >
          <span
            className="inline-block h-5 w-5 rounded bg-accent"
            aria-hidden
          />
          EvalOps
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}
