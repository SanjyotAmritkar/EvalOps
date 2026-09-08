import Link from "next/link";
import { Wordmark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export function TopBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link
          href="/projects"
          className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="EvalOps — projects"
        >
          <Wordmark />
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}
