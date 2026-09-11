import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Same-origin API proxy: `/api/*` is rewritten to the EvalOps FastAPI server.
 *
 * This lives in Proxy (Next.js's current name for what used to be
 * "Middleware") rather than `next.config.ts`'s `rewrites()` deliberately
 * (CP 10.4): Proxy runs per request in the deployed server, so
 * `API_PROXY_TARGET` is read from the *current* process environment on every
 * request. A `next.config.ts` rewrite destination is instead baked into a
 * static manifest at `next build` time -- wrong for a container image built
 * once and run against different API locations (dev, another container, a
 * future deployment) purely via an env var at start time.
 *
 * No secret lives here or reaches the browser: this only decides where the
 * server-to-server proxy call goes.
 */
const DEFAULT_API_PROXY_TARGET = "http://127.0.0.1:8000";

export function proxy(request: NextRequest) {
  const target = process.env.API_PROXY_TARGET ?? DEFAULT_API_PROXY_TARGET;
  const upstream = new URL(target);

  const rewritten = request.nextUrl.clone();
  rewritten.protocol = upstream.protocol;
  rewritten.host = upstream.host;
  rewritten.pathname = request.nextUrl.pathname.replace(/^\/api/, "");

  return NextResponse.rewrite(rewritten);
}

export const config = {
  matcher: "/api/:path*",
};
