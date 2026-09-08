import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "@/lib/api/client";

interface FakeResponseInit {
  ok?: boolean;
  status?: number;
  statusText?: string;
  jsonBody?: unknown;
  jsonThrows?: boolean;
}

function stubFetch(init: FakeResponseInit) {
  const response = {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? "OK",
    json: init.jsonThrows
      ? () => Promise.reject(new Error("invalid json"))
      : () => Promise.resolve(init.jsonBody),
  } as Response;
  const mock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("prefixes /api and sends a JSON content-type", async () => {
    const mock = stubFetch({ jsonBody: [{ id: "p1" }] });

    const data = await apiFetch<Array<{ id: string }>>("/projects");

    expect(data).toEqual([{ id: "p1" }]);
    expect(mock).toHaveBeenCalledWith(
      "/api/projects",
      expect.objectContaining({
        headers: expect.objectContaining({
          "content-type": "application/json",
        }),
      }),
    );
  });

  it("returns undefined for a 204 response", async () => {
    stubFetch({ status: 204, jsonBody: undefined });
    await expect(apiFetch("/projects/p1")).resolves.toBeUndefined();
  });

  it("throws ApiError carrying a string detail (FastAPI 404 shape)", async () => {
    stubFetch({
      ok: false,
      status: 404,
      statusText: "Not Found",
      jsonBody: { detail: "project not found" },
    });

    const error = await apiFetch("/projects/x").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      detail: "project not found",
      fieldErrors: [],
    });
  });

  it("summarises a FastAPI 422 validation array into fieldErrors", async () => {
    stubFetch({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      jsonBody: {
        detail: [
          {
            loc: ["body", "name"],
            msg: "Field required",
            type: "missing",
          },
        ],
      },
    });

    const error = (await apiFetch("/projects").catch(
      (e: unknown) => e,
    )) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.fieldErrors).toEqual([
      { field: "name", message: "Field required" },
    ]);
    expect(error.message).toContain("name: Field required");
  });

  it("falls back to status text when the error body is not JSON", async () => {
    stubFetch({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      jsonThrows: true,
    });

    const error = (await apiFetch("/projects").catch(
      (e: unknown) => e,
    )) as ApiError;

    expect(error.status).toBe(500);
    expect(error.detail).toBe("Internal Server Error");
  });
});
