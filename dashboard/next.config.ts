import type { NextConfig } from "next";

/**
 * The dashboard talks to the EvalOps FastAPI server through a same-origin
 * proxy: every request to `/api/*` reaches the API instead. This keeps the
 * backend free of CORS configuration and keeps the browser origin single.
 *
 * The proxy itself lives in `src/middleware.ts`, not here. `next build`
 * evaluates `rewrites()` once to bake a static routes manifest, so an
 * `API_PROXY_TARGET` read in this function would be frozen at *build* time --
 * wrong for a container image that is built once and run against different
 * API locations (CP 10.4). Middleware re-runs per request in the deployed
 * server (including the standalone `node server.js` this repo ships), so it
 * reads the current environment every time.
 */
const nextConfig: NextConfig = {
  // The repo's guidance lives in the root CLAUDE.md / docs; don't let `next dev`
  // scaffold its own AGENTS.md / CLAUDE.md inside dashboard/.
  agentRules: false,

  // Self-contained production server (CP 10.4): `.next/standalone` bundles only
  // the traced dependencies a plain `node server.js` needs, so the runtime
  // container image carries no `node_modules`, no dev server, and no source
  // mount.
  output: "standalone",
};

export default nextConfig;
