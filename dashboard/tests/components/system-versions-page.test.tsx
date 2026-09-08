import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SystemVersionsPage from "@/app/projects/[projectId]/system-versions/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  usePathname: () => "/projects/p1/system-versions",
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={typeof href === "string" ? href : "#"}>{children}</a>
  ),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const VERSION = {
  id: "v1",
  project_id: "p1",
  name: "support-prompt",
  version: "v1",
  provider: "openai",
  model: "gpt-4o-mini",
  prompt_template: "Q: ${input}",
  parameters: {},
  rag_config: null,
  tool_policy: null,
  created_at: "2026-09-08T12:00:00Z",
};

describe("SystemVersionsPage", () => {
  it("lists system versions with provider and model", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([VERSION])));

    render(<SystemVersionsPage />, { wrapper: makeWrapper() });

    const link = await screen.findByRole("link", { name: "support-prompt" });
    const row = link.closest("tr")!;
    expect(row).toHaveTextContent("openai");
    expect(row).toHaveTextContent("gpt-4o-mini");
  });

  it("blocks submit on invalid parameter JSON, then posts a parsed object", async () => {
    const created = { ...VERSION, id: "v2", name: "new-cfg" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(created, 201))
      .mockResolvedValue(jsonResponse([created]));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<SystemVersionsPage />, { wrapper: makeWrapper() });

    await screen.findByText("No system versions yet");
    await user.click(
      screen.getAllByRole("button", { name: /new system version/i })[0]!,
    );

    await user.type(screen.getByLabelText("Name"), "new-cfg");
    await user.type(screen.getByLabelText("Version"), "v1");
    await user.type(screen.getByLabelText("Model"), "gpt-4o-mini");
    await user.click(screen.getByLabelText("Prompt template"));
    await user.paste("Q: ${input}");

    const params = screen.getByLabelText(/Parameters/);
    await user.click(params);
    await user.paste("{bad");
    expect(await screen.findByText("not valid JSON")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create system version" }),
    ).toBeDisabled();

    await user.clear(params);
    await user.click(params);
    await user.paste('{"temperature": 0}');

    const submit = screen.getByRole("button", {
      name: "Create system version",
    });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await screen.findByRole("link", { name: "new-cfg" });

    const post = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/projects/p1/system-versions");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({
      name: "new-cfg",
      version: "v1",
      provider: "openai",
      model: "gpt-4o-mini",
      prompt_template: "Q: ${input}",
      parameters: { temperature: 0 },
      rag_config: null,
      tool_policy: null,
    });
  });
});
