import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HelpProvider, useHelp } from "@/components/help/help-provider";

function OpenButton() {
  const { openHelp } = useHelp();
  return (
    <button type="button" onClick={openHelp}>
      Open help
    </button>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Help drawer", () => {
  it("opens from the trigger, shows the key glossary, and closes on Escape", async () => {
    const user = userEvent.setup();
    render(
      <HelpProvider>
        <OpenButton />
      </HelpProvider>,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open help" }));

    const dialog = screen.getByRole("dialog", { name: "EvalOps help" });
    for (const term of [
      "Dataset",
      "System version",
      "Experiment",
      "Release policy",
      "Output / RAG / agent evaluation",
      "PASS",
      "BLOCK",
      "Inconclusive / weak statistical evidence",
      "Production traces",
      "Judge calibration",
    ]) {
      expect(within(dialog).getByText(term)).toBeInTheDocument();
    }
    // plain language first
    expect(dialog).toHaveTextContent(
      /A fixed set of example inputs that defines the behaviour/,
    );

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on the close button and via the backdrop", async () => {
    const user = userEvent.setup();
    render(
      <HelpProvider>
        <OpenButton />
      </HelpProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Open help" }));
    await user.click(screen.getAllByRole("button", { name: "Close" })[0]!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
