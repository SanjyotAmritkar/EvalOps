"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { LaptopIcon, MoonIcon, SunIcon } from "@/components/icons";
import { cn } from "@/lib/cn";

const ORDER = ["system", "light", "dark"] as const;
type ThemeChoice = (typeof ORDER)[number];

const LABELS: Record<ThemeChoice, string> = {
  system: "System theme",
  light: "Light theme",
  dark: "Dark theme",
};

const ICONS: Record<ThemeChoice, typeof SunIcon> = {
  system: LaptopIcon,
  light: SunIcon,
  dark: MoonIcon,
};

const noop = () => () => {};

/** false during SSR and first paint, true once hydrated — no setState-in-effect. */
function useHydrated(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const hydrated = useHydrated();

  const current: ThemeChoice =
    theme === "light" || theme === "dark" ? theme : "system";

  function cycle() {
    const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
    setTheme(next ?? "system");
  }

  const Icon = ICONS[current];

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={
        hydrated ? `${LABELS[current]} — click to change` : "Change theme"
      }
      title={hydrated ? LABELS[current] : undefined}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-fg-muted",
        "transition-colors duration-150 hover:bg-surface-raised hover:text-fg",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {/* Stable icon until hydrated to avoid an SSR/client mismatch. */}
      {hydrated ? <Icon /> : <LaptopIcon />}
      <span className="sr-only">Toggle theme</span>
    </button>
  );
}
