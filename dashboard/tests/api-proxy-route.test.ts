import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DELETE,
  GET,
  HEAD,
  OPTIONS,
  PATCH,
  POST,
  PUT,
} from "@/app/api/[...path]/route";

/**
 * The `/api/*` proxy is now a Node.js-runtime Route Handler doing a real
 * server-side `fetch()` (CP 10.4 follow-up), not a Proxy/Middleware rewrite --
 * see the route file's docstring for why. These cover exactly what the spec
 * asked for: path/query forwarding, method/body forwarding, upstream response
 * pass-through, and a clean failure mode on a network error.
 */

function ctx(...path: string[]) {
  return { params: Promise.resolve({ path }) };
}

function request(
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
): NextRequest {
  return new NextRequest(new URL(url, "http://localhost:3000"), init);
}

type FetchMock = ReturnType<typeof vi.fn<(url: URL, init: RequestInit) => Promise<Response>>>;

function stubFetch(response: Response | (() => Response)): FetchMock {
  const fetchMock: FetchMock = vi.fn(async (_url: URL, _init: RequestInit) =>
    typeof response === "function" ? response() : response,
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("api proxy route — path and query forwarding", () => {
  it("forwards the path and query string to API_PROXY_TARGET", async () => {
    vi.stubEnv("API_PROXY_TARGET", "http://api:8000");
    const fetchMock = stubFetch(new Response("[]", { status: 200 }));

    await GET(
      request("/api/experiments/e1/runs?limit=5&offset=10"),
      ctx("experiments", "e1", "runs"),
    );

    const [calledUrl] = fetchMock.mock.calls[0]!;
    expect(calledUrl.toString()).toBe(
      "http://api:8000/experiments/e1/runs?limit=5&offset=10",
    );
  });

  it("falls back to 127.0.0.1:8000 when API_PROXY_TARGET is unset", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(request("/api/projects"), ctx("projects"));
    const [calledUrl] = fetchMock.mock.calls[0]!;
    expect(calledUrl.toString()).toBe("http://127.0.0.1:8000/projects");
  });

  it("re-reads the environment on every call, not frozen at first use", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));

    vi.stubEnv("API_PROXY_TARGET", "http://api:8000");
    await GET(request("/api/projects"), ctx("projects"));
    vi.stubEnv("API_PROXY_TARGET", "http://staging-api:9000");
    await GET(request("/api/projects"), ctx("projects"));

    const urls = fetchMock.mock.calls.map(([u]) => (u as URL).toString());
    expect(urls).toEqual([
      "http://api:8000/projects",
      "http://staging-api:9000/projects",
    ]);
  });

  it("percent-encodes path segments", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(
      request("/api/datasets/a b"),
      ctx("datasets", "a b"),
    );
    const [calledUrl] = fetchMock.mock.calls[0]!;
    expect(calledUrl.pathname).toBe("/datasets/a%20b");
  });
});

describe("api proxy route — method and body forwarding", () => {
  it("forwards a POST body and the method, with a JSON content-type", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 201 }));
    await POST(
      request("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: '{"name":"demo"}',
      }),
      ctx("projects"),
    );

    const [, init] = fetchMock.mock.calls[0]!;
    expect(init.method).toBe("POST");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(
      '{"name":"demo"}',
    );
    expect((init.headers as Headers).get("content-type")).toBe(
      "application/json",
    );
  });

  it.each(["PUT", "PATCH", "DELETE"])("forwards a %s body", async (method) => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    const handler = { PUT, PATCH, DELETE }[method]!;
    await handler(
      request("/api/release-policies/rp1", {
        method,
        body: '{"name":"updated"}',
      }),
      ctx("release-policies", "rp1"),
    );
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init.method).toBe(method);
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(
      '{"name":"updated"}',
    );
  });

  it("never attaches a body for GET or HEAD", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(request("/api/projects"), ctx("projects"));
    await HEAD(request("/api/projects"), ctx("projects"));
    for (const [, init] of fetchMock.mock.calls) {
      expect(init.body).toBeUndefined();
    }
  });

  it("forwards OPTIONS", async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }));
    await OPTIONS(request("/api/projects", { method: "OPTIONS" }), ctx("projects"));
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init.method).toBe("OPTIONS");
  });

  it("does not forward hop-by-hop headers, host, or content-length upstream", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(
      request("/api/projects", {
        headers: {
          host: "dashboard.example.com",
          connection: "keep-alive",
          "content-length": "0",
          "accept-encoding": "gzip",
          "x-request-id": "abc123",
        },
      }),
      ctx("projects"),
    );
    const [, init] = fetchMock.mock.calls[0]!;
    const headers = init.headers as Headers;
    expect(headers.has("host")).toBe(false);
    expect(headers.has("connection")).toBe(false);
    expect(headers.has("content-length")).toBe(false);
    expect(headers.has("accept-encoding")).toBe(false);
    // a genuinely useful header (CP 10.3 correlation) still passes through
    expect(headers.get("x-request-id")).toBe("abc123");
  });
});

describe("api proxy route — upstream response pass-through", () => {
  it("returns the upstream status, body, and content-type", async () => {
    stubFetch(
      new Response(JSON.stringify({ id: "p1" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    const response = await POST(
      request("/api/projects", { method: "POST", body: "{}" }),
      ctx("projects"),
    );
    expect(response.status).toBe(201);
    expect(response.headers.get("content-type")).toBe("application/json");
    expect(await response.json()).toEqual({ id: "p1" });
  });

  it("propagates the X-Request-ID the API generated back to the browser", async () => {
    stubFetch(
      new Response("{}", {
        status: 200,
        headers: { "x-request-id": "server-generated-id" },
      }),
    );
    const response = await GET(request("/api/projects"), ctx("projects"));
    expect(response.headers.get("x-request-id")).toBe("server-generated-id");
  });

  it("strips content-encoding and content-length from the forwarded response", async () => {
    stubFetch(
      new Response("{}", {
        status: 200,
        headers: { "content-encoding": "gzip", "content-length": "123" },
      }),
    );
    const response = await GET(request("/api/projects"), ctx("projects"));
    expect(response.headers.has("content-encoding")).toBe(false);
    expect(response.headers.has("content-length")).toBe(false);
  });

  it("passes through a non-2xx upstream response unchanged (e.g. 404)", async () => {
    stubFetch(
      new Response(JSON.stringify({ detail: "project not found" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );
    const response = await GET(request("/api/projects/nope"), ctx("projects", "nope"));
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ detail: "project not found" });
  });
});

describe("api proxy route — server-side API-key injection (CP 10.5)", () => {
  it("attaches Authorization: Bearer <key> when EVALOPS_API_KEY is configured", async () => {
    vi.stubEnv("EVALOPS_API_KEY", "s3cr3t-server-key");
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));

    await GET(request("/api/projects"), ctx("projects"));

    const [, init] = fetchMock.mock.calls[0]!;
    expect((init.headers as Headers).get("authorization")).toBe(
      "Bearer s3cr3t-server-key",
    );
  });

  it("sends no Authorization header when EVALOPS_API_KEY is unset", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(request("/api/projects"), ctx("projects"));
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init.headers as Headers).has("authorization")).toBe(false);
  });

  it("overrides whatever Authorization the browser sent -- the server decides, never the client", async () => {
    vi.stubEnv("EVALOPS_API_KEY", "s3cr3t-server-key");
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));

    await GET(
      request("/api/projects", {
        headers: { authorization: "Bearer whatever-the-browser-sent" },
      }),
      ctx("projects"),
    );

    const [, init] = fetchMock.mock.calls[0]!;
    expect((init.headers as Headers).get("authorization")).toBe(
      "Bearer s3cr3t-server-key",
    );
  });

  it("drops a browser-supplied Authorization header when no key is configured", async () => {
    const fetchMock = stubFetch(new Response("{}", { status: 200 }));
    await GET(
      request("/api/projects", {
        headers: { authorization: "Bearer whatever-the-browser-sent" },
      }),
      ctx("projects"),
    );
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init.headers as Headers).has("authorization")).toBe(false);
  });

  it("never lets the configured key reach the response returned to the browser", async () => {
    vi.stubEnv("EVALOPS_API_KEY", "s3cr3t-server-key");
    stubFetch(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    const response = await GET(request("/api/projects"), ctx("projects"));

    const bodyText = await response.text();
    expect(bodyText).not.toContain("s3cr3t-server-key");
    for (const [key, value] of response.headers.entries()) {
      expect(`${key}:${value}`).not.toContain("s3cr3t-server-key");
    }
  });
});

describe("api proxy route — upstream/network failure", () => {
  it("returns a clean 502 without leaking the underlying error", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connect ECONNREFUSED 10.0.0.5:8000 secret-internal-host");
      }),
    );

    const response = await GET(request("/api/projects"), ctx("projects"));

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body).toEqual({ detail: "The API is temporarily unreachable." });
    expect(JSON.stringify(body)).not.toContain("10.0.0.5");
    consoleError.mockRestore();
  });
});
