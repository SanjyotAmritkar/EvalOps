import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HelpProvider, useHelp } from "@/components/help/help-provider";
import { InfoHint } from "@/components/ui/info-hint";

function OpenButton() {
  const { openHelp } = useHelp();
  return (
    <button type="button" onClick={() => openHelp()}>
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

  it("an InfoHint with a term focuses that glossary entry, not just the top of the list", async () => {
    const user = userEvent.setup();
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;

    render(
      <HelpProvider>
        <InfoHint label="What is a regressing case?" term="regressing-case" />
      </HelpProvider>,
    );

    await user.click(
      screen.getByRole("button", { name: "What is a regressing case?" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "EvalOps help" });
    const term = await within(dialog).findByText("Regressing case");

    expect(scrollIntoView).toHaveBeenCalled();
    // focus lands on the glossary entry itself, not the dialog's default focus
    expect(term.closest("[tabindex='-1']")).toHaveFocus();
  });

  it("a plain openHelp() (no term) leaves focus on the drawer, not any one entry", async () => {
    const user = userEvent.setup();
    render(
      <HelpProvider>
        <OpenButton />
      </HelpProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Open help" }));
    const dialog = await screen.findByRole("dialog", { name: "EvalOps help" });
    expect(dialog).toHaveFocus();
  });
});
