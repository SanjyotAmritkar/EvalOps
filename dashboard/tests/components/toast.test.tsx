import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "@/components/ui/toast";

function Trigger({ message, tone }: { message: string; tone?: "success" | "error" | "info" }) {
  const { toast } = useToast();
  return (
    <button type="button" onClick={() => toast(message, tone)}>
      fire
    </button>
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ToastProvider", () => {
  it("shows a transient message in a polite live region and lets you dismiss it", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <Trigger message="Project created" />
      </ToastProvider>,
    );

    await user.click(screen.getByRole("button", { name: "fire" }));
    const toast = await screen.findByText("Project created");
    expect(toast.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Project created")).not.toBeInTheDocument();
  });

  it("stacks multiple messages", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <Trigger message="First" />
      </ToastProvider>,
    );
    const fire = screen.getByRole("button", { name: "fire" });
    await user.click(fire);
    await user.click(fire);
    expect(screen.getAllByText("First")).toHaveLength(2);
  });

  it("is a safe no-op when used outside a provider", async () => {
    const user = userEvent.setup();
    render(<Trigger message="nothing happens" />);
    await user.click(screen.getByRole("button", { name: "fire" }));
    expect(screen.queryByText("nothing happens")).not.toBeInTheDocument();
  });
});
