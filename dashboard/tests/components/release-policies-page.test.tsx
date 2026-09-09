import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReleasePoliciesPage from "@/app/projects/[projectId]/release-policies/page";
import { jsonResponse, makeWrapper } from "../test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1" }),
  usePathname: () => "/projects/p1/release-policies",
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const POLICY = {
  id: "rp1",
  name: "latency-budget",
  thresholds: { "latency_ms.p95": 0.1 },
  max_safety_violations: 0,
};

describe("ReleasePoliciesPage", () => {
  it("shows the global scope note, the fraction meaning, and the inert-safety note", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([POLICY])));

    render(<ReleasePoliciesPage />, { wrapper: makeWrapper() });

    expect(
      await screen.findByText("latency-budget"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/defined globally and can be attached to experiments/i),
    ).toBeInTheDocument();
    // friendly metric name + human-language threshold, raw key kept as detail
    expect(screen.getByText("P95 latency")).toBeInTheDocument();
    expect(screen.getByText("latency_ms.p95")).toBeInTheDocument();
    expect(screen.getByText("Up to 10% regression")).toBeInTheDocument();
    expect(
      screen.getByText(/Safety metrics are not evaluated yet/i),
    ).toBeInTheDocument();
  });

  it("creates a policy from the threshold rows", async () => {
    const created = {
      id: "rp2",
      name: "quality-floor",
      thresholds: { success_rate: 0.05 },
      max_safety_violations: 0,
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(created, 201))
      .mockResolvedValue(jsonResponse([created]));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<ReleasePoliciesPage />, { wrapper: makeWrapper() });

    await screen.findByText("No release policies yet");
    await user.click(screen.getAllByRole("button", { name: /new policy/i })[0]!);

    await user.type(screen.getByLabelText("Name"), "quality-floor");
    await user.type(
      screen.getByLabelText("Threshold 1 metric"),
      "success_rate",
    );
    await user.type(screen.getByLabelText("Threshold 1 value"), "0.05");

    const submit = screen.getByRole("button", { name: "Create policy" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    expect(await screen.findByText("quality-floor")).toBeInTheDocument();

    const post = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(post?.[0]).toBe("/api/release-policies");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({
      name: "quality-floor",
      thresholds: { success_rate: 0.05 },
      max_safety_violations: 0,
    });
  });
});
