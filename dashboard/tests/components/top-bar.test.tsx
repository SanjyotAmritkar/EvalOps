import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HelpProvider } from "@/components/help/help-provider";
import { TopBar } from "@/components/layout/top-bar";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", setTheme: vi.fn() }),
}));

afterEach(() => vi.restoreAllMocks());

describe("TopBar", () => {
  it("links the wordmark to /projects and opens Help", async () => {
    const user = userEvent.setup();
    render(
      <HelpProvider>
        <TopBar />
      </HelpProvider>,
    );

    expect(
      screen.getByRole("link", { name: /EvalOps — projects/i }),
    ).toHaveAttribute("href", "/projects");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Help" }));
    expect(
      screen.getByRole("dialog", { name: "EvalOps help" }),
    ).toBeInTheDocument();
  });
});
