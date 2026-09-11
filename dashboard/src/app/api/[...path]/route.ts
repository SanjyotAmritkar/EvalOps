import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Same-origin API proxy: every request to `/api/*` is forwarded, server-side,
 * to the EvalOps FastAPI server. This keeps the backend free of CORS
 * configuration and keeps the browser origin single.
 *
 * A server-side `fetch()` route handler, not a Proxy (`src/proxy.ts`,
 * removed) rewrite or a `next.config.ts` rewrite. Two reasons:
 *
 * 1. `API_PROXY_TARGET` must be read at *request* time, not baked into a
 *    static manifest at `next build` time -- the same built image is run
 *    against different API locations purely via an env var at container
 *    start (see docs/ARCHITECTURE.md CP 10.4).
 * 2. Route Handlers run in the Node.js runtime by default (pinned explicitly
 *    below); Proxy/Middleware runs in the restricted Edge runtime by default.
 *    A `NextResponse.rewrite()` to an *external* absolute origin from the
 *    Edge runtime returned HTTP 500 in one production environment (Azure)
 *    while working locally -- a real `fetch()` from plain Node.js has none of
 *    that runtime's constraints and is the same code path everywhere.
 *
 * `API_PROXY_TARGET` is read only here, server-side; it is never sent to the
 * browser or referenced by client code.
 *
 * CP 10.5: when the API requires a key, `EVALOPS_API_KEY` is likewise read
 * only here (never a `NEXT_PUBLIC_*` variable, never referenced by client
 * code) and attached as `Authorization: Bearer <key>` on the *outgoing*
 * request to FastAPI -- the browser never sees it, and cannot influence it
 * either: any `Authorization` header the browser sent is stripped first.
 */
export const runtime = "nodejs";
// A proxy response must never be served from a cache or statically optimized.
export const dynamic = "force-dynamic";

const DEFAULT_API_PROXY_TARGET = "http://127.0.0.1:8000";

//: RFC 7230 §6.1 hop-by-hop headers -- meaningful only for one physical
// connection, never valid to forward across a proxy in either direction.
const HOP_BY_HOP_HEADERS = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

// Request-only: recomputed by `fetch()` itself from the target URL / body, or
// would otherwise leak this server's negotiation to the upstream unnecessarily.
// `authorization` is stripped unconditionally -- this server decides what
// credential (if any) reaches the API, never the browser.
const STRIP_FROM_REQUEST = [
  ...HOP_BY_HOP_HEADERS,
  "host",
  "content-length",
  "accept-encoding",
  "authorization",
];

// Response-only: the body may no longer match these once it has passed
// through `fetch()` (which transparently decodes a compressed response), and
// the final length/connection is this server's to decide, not FastAPI's.
const STRIP_FROM_RESPONSE = [...HOP_BY_HOP_HEADERS, "content-encoding", "content-length"];

function filteredHeaders(source: Headers, strip: readonly string[]): Headers {
  const blocked = new Set(strip);
  const out = new Headers();
  source.forEach((value, key) => {
    if (!blocked.has(key.toLowerCase())) {
      out.append(key, value);
    }
  });
  return out;
}

function upstreamUrl(pathSegments: string[], search: string): URL {
  const target = process.env.API_PROXY_TARGET ?? DEFAULT_API_PROXY_TARGET;
  const url = new URL(target);
  url.pathname = `/${pathSegments.map(encodeURIComponent).join("/")}`;
  url.search = search;
  return url;
}

const METHODS_WITHOUT_BODY = new Set(["GET", "HEAD"]);

async function handle(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  const url = upstreamUrl(path, request.nextUrl.search);

  const headers = filteredHeaders(request.headers, STRIP_FROM_REQUEST);
  const apiKey = process.env.EVALOPS_API_KEY;
  if (apiKey) {
    headers.set("authorization", `Bearer ${apiKey}`);
  }

  const init: RequestInit = { method: request.method, headers };
  if (!METHODS_WITHOUT_BODY.has(request.method) && request.body !== null) {
    // The dashboard only ever sends small JSON bodies (see lib/api/client.ts)
    // -- buffering is simpler and easier to test than streaming with the
    // `duplex: "half"` option a piped ReadableStream body would require, at
    // no practical cost here.
    const buffered = await request.arrayBuffer();
    if (buffered.byteLength > 0) {
      init.body = buffered;
    }
  }

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(url, init);
  } catch (error) {
    // Never forward the raw error (it can include connection strings/host
    // details); log a bounded message server-side and tell the client only
    // that the upstream was unreachable.
    console.error(
      "api proxy: upstream request failed:",
      error instanceof Error ? error.message : "unknown error",
    );
    return NextResponse.json(
      { detail: "The API is temporarily unreachable." },
      { status: 502 },
    );
  }

  return new NextResponse(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: filteredHeaders(upstreamResponse.headers, STRIP_FROM_RESPONSE),
  });
}

export {
  handle as DELETE,
  handle as GET,
  handle as HEAD,
  handle as OPTIONS,
  handle as PATCH,
  handle as POST,
  handle as PUT,
};
