import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProjectsPage from "@/app/projects/page";
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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ProjectsPage", () => {
  it("shows a loading state, then the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));

    render(<ProjectsPage />, { wrapper: makeWrapper() });

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("renders each project as a link into its workspace", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([PROJECT])));

    render(<ProjectsPage />, { wrapper: makeWrapper() });

    const link = await screen.findByRole("link", { name: /Support Assistant/ });
    expect(link).toHaveAttribute("href", "/projects/p1");
  });

  it("surfaces an API failure with a retry affordance", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "database is down" }, 500),
      ),
    );

    render(<ProjectsPage />, { wrapper: makeWrapper() });

    expect(
      await screen.findByText("Could not load projects"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("POSTs the trimmed name, shows the new project, and clears the input", async () => {
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
    render(<ProjectsPage />, { wrapper: makeWrapper() });

    const input = await screen.findByLabelText("New project");
    await user.type(input, "  New App  ");
    await user.click(
      screen.getByRole("button", { name: /create project/i }),
    );

    expect(await screen.findByText("New App")).toBeInTheDocument();
    await waitFor(() =>
      expect((input as HTMLInputElement).value).toBe(""),
    );

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
    render(<ProjectsPage />, { wrapper: makeWrapper() });

    const input = await screen.findByLabelText("New project");
    await user.type(input, "x");
    await user.click(
      screen.getByRole("button", { name: /create project/i }),
    );

    expect(
      await screen.findByText("name must be non-empty"),
    ).toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe("x");
  });
});
