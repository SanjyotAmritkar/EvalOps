import Link from "next/link";
import { Wordmark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { HelpButton } from "./help-button";

export function TopBar() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 sm:px-8">
        <Link
          href="/projects"
          className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="EvalOps — projects"
        >
          <Wordmark />
        </Link>
        <div className="flex items-center gap-2">
          <HelpButton />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
