import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceTabs } from "@/components/layout/workspace-tabs";

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

describe("WorkspaceTabs", () => {
  it("renders every project section as a link", () => {
    render(<WorkspaceTabs projectId="p1" />);
    for (const label of [
      "Overview",
      "Datasets",
      "System Versions",
      "Experiments",
      "Release Policies",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("marks Overview active only on the exact project route", () => {
    routerState.pathname = "/projects/p1";
    render(<WorkspaceTabs projectId="p1" />);
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
    render(<WorkspaceTabs projectId="p1" />);
    expect(screen.getByRole("link", { name: "Datasets" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("link", { name: "Overview" }),
    ).not.toHaveAttribute("aria-current");
  });
});
