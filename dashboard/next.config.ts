import type { NextConfig } from "next";

/**
 * The dashboard talks to the EvalOps FastAPI server through a same-origin
 * proxy: every request to `/api/*` reaches the API instead. This keeps the
 * backend free of CORS configuration and keeps the browser origin single.
 *
 * The proxy itself is the Node.js-runtime Route Handler at
 * `src/app/api/[...path]/route.ts`, not this file: a `rewrites()` entry here
 * is evaluated once at `next build` and baked into a static manifest, which
 * would freeze `API_PROXY_TARGET` at build time -- wrong for a container
 * image built once and run against different API locations (CP 10.4). See
 * that route handler's docstring for the rest of the reasoning (it also
 * avoids an Edge-runtime rewrite failure seen in production).
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
