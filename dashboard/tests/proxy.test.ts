import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy } from "@/proxy";

/**
 * The proxy's whole job (CP 10.4) is to read API_PROXY_TARGET at *request*
 * time -- not once at build time, the way a next.config.ts rewrite would.
 * These exercise that directly, including the failure mode a static rewrite
 * manifest cannot express: the same running server following an env change.
 */

afterEach(() => {
  vi.unstubAllEnvs();
});

function requestFor(path: string): NextRequest {
  return new NextRequest(new URL(path, "http://localhost:3000"));
}

describe("proxy", () => {
  it("rewrites /api/* to API_PROXY_TARGET", () => {
    vi.stubEnv("API_PROXY_TARGET", "http://api:8000");
    const response = proxy(requestFor("/api/projects"));
    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://api:8000/projects",
    );
  });

  it("preserves the query string", () => {
    vi.stubEnv("API_PROXY_TARGET", "http://api:8000");
    const response = proxy(requestFor("/api/experiments/e1/runs?limit=5"));
    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://api:8000/experiments/e1/runs?limit=5",
    );
  });

  it("falls back to 127.0.0.1:8000 when API_PROXY_TARGET is unset", () => {
    vi.stubEnv("API_PROXY_TARGET", "");
    vi.unstubAllEnvs(); // ensure truly unset, not ""
    const response = proxy(requestFor("/api/projects"));
    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://127.0.0.1:8000/projects",
    );
  });

  it("re-reads the environment on every call — not frozen at first use", () => {
    vi.stubEnv("API_PROXY_TARGET", "http://api:8000");
    expect(proxy(requestFor("/api/projects")).headers.get("x-middleware-rewrite")).toBe(
      "http://api:8000/projects",
    );

    vi.stubEnv("API_PROXY_TARGET", "http://staging-api:9000");
    expect(proxy(requestFor("/api/projects")).headers.get("x-middleware-rewrite")).toBe(
      "http://staging-api:9000/projects",
    );
  });
});
