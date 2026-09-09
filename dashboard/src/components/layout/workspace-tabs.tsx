"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

export function WorkspaceTabs({ projectId }: { projectId: string }) {
  const pathname = usePathname() ?? "";
  const base = `/projects/${projectId}`;

  const tabs = [
    { label: "Overview", href: base, active: pathname === base },
    {
      label: "Datasets",
      href: `${base}/datasets`,
      active: pathname.startsWith(`${base}/datasets`),
    },
    {
      label: "System Versions",
      href: `${base}/system-versions`,
      active: pathname.startsWith(`${base}/system-versions`),
    },
    {
      label: "Experiments",
      href: `${base}/experiments`,
      active: pathname.startsWith(`${base}/experiments`),
    },
    {
      label: "Release Policies",
      href: `${base}/release-policies`,
      active: pathname.startsWith(`${base}/release-policies`),
    },
    {
      label: "Judge Calibration",
      href: `${base}/judge-calibrations`,
      active: pathname.startsWith(`${base}/judge-calibrations`),
    },
  ];

  return (
    <nav
      aria-label="Project sections"
      className="flex gap-1 overflow-x-auto border-b border-border"
    >
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          aria-current={tab.active ? "page" : undefined}
          className={cn(
            "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            tab.active
              ? "border-accent text-fg"
              : "border-transparent text-fg-muted hover:text-fg",
          )}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
