"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";

interface NavItem {
  label: string;
  path: string;
  exact?: boolean;
}

interface NavGroup {
  label?: string;
  items: NavItem[];
}

/** Grouped project navigation. Routes are unchanged from the old tab bar. */
export function projectNavGroups(base: string): NavGroup[] {
  return [
    { items: [{ label: "Overview", path: base, exact: true }] },
    {
      label: "Evaluate",
      items: [
        { label: "Experiments", path: `${base}/experiments` },
        { label: "Datasets", path: `${base}/datasets` },
        { label: "System Versions", path: `${base}/system-versions` },
      ],
    },
    {
      label: "Production",
      items: [{ label: "Production Traces", path: `${base}/traces` }],
    },
    {
      label: "Configuration",
      items: [{ label: "Release Policies", path: `${base}/release-policies` }],
    },
    {
      label: "Advanced",
      items: [{ label: "Judge Calibration", path: `${base}/judge-calibrations` }],
    },
  ];
}

function isActive(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.path : pathname.startsWith(item.path);
}

/** The label of the section the current route belongs to (for the mobile summary). */
export function activeSectionLabel(pathname: string, projectId: string): string {
  const groups = projectNavGroups(`/projects/${projectId}`);
  for (const group of groups) {
    for (const item of group.items) {
      if (isActive(pathname, item)) return item.label;
    }
  }
  return "Overview";
}

export function ProjectNav({ projectId }: { projectId: string }) {
  const pathname = usePathname() ?? "";
  const groups = projectNavGroups(`/projects/${projectId}`);

  return (
    <nav aria-label="Project sections" className="flex flex-col gap-5">
      {groups.map((group, groupIndex) => (
        <div key={group.label ?? `group-${groupIndex}`} className="flex flex-col gap-1">
          {group.label ? (
            <p className="px-2 pb-1 text-[12px] font-semibold uppercase tracking-wide text-fg-subtle">
              {group.label}
            </p>
          ) : null}
          {group.items.map((item) => {
            const active = isActive(pathname, item);
            return (
              <Link
                key={item.path}
                href={item.path}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-[15px] font-medium transition-colors",
                  active
                    ? "bg-surface-raised text-fg"
                    : "text-fg-muted hover:bg-surface-raised hover:text-fg",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
