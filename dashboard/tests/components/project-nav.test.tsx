import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ProjectNav,
  activeSectionLabel,
  projectNavGroups,
} from "@/components/layout/project-nav";

const routerState = vi.hoisted(() => ({ pathname: "/projects/p1" }));

vi.mock("next/navigation", () => ({
  usePathname: () => routerState.pathname,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"} {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  routerState.pathname = "/projects/p1";
});

describe("ProjectNav", () => {
  it("renders grouped sections with every existing route preserved", () => {
    render(<ProjectNav projectId="p1" />);

    for (const heading of ["Evaluate", "Production", "Configuration", "Advanced"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }

    const expected: Record<string, string> = {
      Overview: "/projects/p1",
      Experiments: "/projects/p1/experiments",
      Datasets: "/projects/p1/datasets",
      "System Versions": "/projects/p1/system-versions",
      "Production Traces": "/projects/p1/traces",
      "Release Policies": "/projects/p1/release-policies",
      "Judge Calibration": "/projects/p1/judge-calibrations",
    };
    for (const [label, href] of Object.entries(expected)) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute(
        "href",
        href,
      );
    }
  });

  it("marks Overview active only on the exact project route", () => {
    routerState.pathname = "/projects/p1";
    render(<ProjectNav projectId="p1" />);
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("link", { name: "Datasets" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("marks a section active for any nested route under it", () => {
    routerState.pathname = "/projects/p1/datasets/abc123";
    render(<ProjectNav projectId="p1" />);
    expect(screen.getByRole("link", { name: "Datasets" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("link", { name: "Overview" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("has no horizontally scrolling container", () => {
    render(<ProjectNav projectId="p1" />);
    const nav = screen.getByRole("navigation", { name: "Project sections" });
    expect(nav.className).not.toMatch(/overflow-x-auto/);
  });

  it("activeSectionLabel resolves the current section for the mobile summary", () => {
    expect(activeSectionLabel("/projects/p1", "p1")).toBe("Overview");
    expect(
      activeSectionLabel("/projects/p1/system-versions/xyz", "p1"),
    ).toBe("System Versions");
    expect(activeSectionLabel("/projects/p1/traces", "p1")).toBe(
      "Production Traces",
    );
  });

  it("projectNavGroups keeps Overview / Evaluate / Production / Configuration / Advanced order", () => {
    const groups = projectNavGroups("/projects/p1");
    expect(groups.map((g) => g.label)).toEqual([
      undefined,
      "Evaluate",
      "Production",
      "Configuration",
      "Advanced",
    ]);
  });
});
