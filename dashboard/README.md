# EvalOps dashboard

The web console for EvalOps: projects, datasets, system versions, experiments
(decision-first results, statistical evidence, regression diagnostics),
release policies, production traces (capture → promote → replay), RAG/agent
evaluation, and judge calibration — every number rendered comes from the
FastAPI API; no metric or gate decision is computed in the browser. See the
root [README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)
for the full picture.

## Stack

- Next.js 16 (App Router) + React 19 + TypeScript
- Tailwind CSS v4 (CSS-first config, class-based dark mode)
- TanStack Query for data fetching, `next-themes` for the light/dark/system toggle
- Vitest + Testing Library for unit/component tests

## Develop

```bash
npm install          # first time
npm run dev          # http://localhost:3000  -> redirects to /projects
```

The dashboard proxies every `/api/*` request to the EvalOps API. Point it at a
running server (default `http://127.0.0.1:8000`):

```bash
cp .env.example .env.local     # optional; edit API_PROXY_TARGET if needed
```

Start the API from the repository root (`make api`, needs `DATABASE_URL` and
`alembic upgrade head` — see the root README).

## Checks

```bash
npm run lint         # eslint (flat config, eslint-config-next)
npm run typecheck    # tsc --noEmit
npm run test         # vitest run
npm run build        # next build
npm run check        # all of the above
```

CI runs `npm run check` on Node 22. Nothing here talks to a real model or a real
database — component tests stub `fetch`.
