import type { NextConfig } from "next";

/**
 * The dashboard talks to the EvalOps FastAPI server through a same-origin
 * proxy: every request to `/api/*` is rewritten to the API. This keeps the
 * backend free of CORS configuration and keeps the browser origin single.
 */
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
