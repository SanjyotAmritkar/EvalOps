import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProjectsPage from "@/app/projects/page";
import { ToastProvider } from "@/components/ui/toast";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

const PROJECT = {
  id: "p1",
  name: "Support Assistant",
  created_at: "2026-09-08T12:00:00Z",
};

function renderPage() {
  const Wrapper = makeWrapper();
  return render(
    <Wrapper>
      <ToastProvider>
        <ProjectsPage />
      </ToastProvider>
    </Wrapper>,
  );
}

/** The <form>'s submit button, distinct from the hero CTA of the same name. */
function submitButton() {
  const input = screen.getByLabelText("New project");
  const form = input.closest("form")!;
  return within(form).getByRole("button", { name: /create project/i });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProjectsPage — onboarding", () => {
  it("leads with the hero, the how-it-works steps, and both CTAs", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
    renderPage();

    expect(
      screen.getByRole("heading", {
        name: /ship ai system changes with confidence/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "How EvalOps works" }),
    ).toBeInTheDocument();
    // the 5 steps
    for (const step of [
      "Dataset",
      "System versions",
      "Evaluate",
      "Analyze",
      "Release",
    ]) {
      expect(screen.getByText(step)).toBeInTheDocument();
    }
    // secondary CTA is an anchor to the same-page section
    expect(
      screen.getByRole("link", { name: "How EvalOps works" }),
    ).toHaveAttribute("href", "#how-it-works");

    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("the hero CTA focuses the create field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
    const user = userEvent.setup();
    renderPage();

    await user.click(
      screen.getAllByRole("button", { name: /create project/i })[0]!,
    );
    expect(screen.getByLabelText("New project")).toHaveFocus();
  });

  it("renders each project as a link into its workspace", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([PROJECT])));
    renderPage();

    const link = await screen.findByRole("link", { name: /Support Assistant/ });
    expect(link).toHaveAttribute("href", "/projects/p1");
  });

  it("surfaces an API failure with a retry affordance", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "database is down" }, 500)),
    );
    renderPage();

    expect(
      await screen.findByText("Could not load projects"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("POSTs the trimmed name, toasts, shows the project, and clears the input", async () => {
    const created = {
      id: "p2",
      name: "New App",
      created_at: "2026-09-08T13:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(created, 201))
      .mockResolvedValue(jsonResponse([created]));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByLabelText("New project");
    await user.type(input, "  New App  ");
    await user.click(submitButton());

    expect(await screen.findByText("New App")).toBeInTheDocument();
    expect(
      await screen.findByText(/Project .*New App.* created/),
    ).toBeInTheDocument();
    await waitFor(() => expect((input as HTMLInputElement).value).toBe(""));

    const postCall = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(postCall?.[0]).toBe("/api/projects");
    expect(
      JSON.parse((postCall?.[1] as RequestInit).body as string),
    ).toEqual({ name: "New App" });
  });

  it("shows a validation message from the API without clearing the input", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse({ detail: "name must be non-empty" }, 422),
      );
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByLabelText("New project");
    await user.type(input, "x");
    await user.click(submitButton());

    expect(
      await screen.findByText("name must be non-empty"),
    ).toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe("x");
  });
});
