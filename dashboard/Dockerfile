# EvalOps dashboard image (Phase 10, CP 10.4).
#
# Multi-stage build producing a self-contained Next.js "standalone" server --
# no dev server, no node_modules in the runtime layer beyond what tracing
# actually needs. Node version matches .nvmrc / CI (actions/setup-node@v4,
# node-version: "22").

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# API_PROXY_TARGET is read at server *start* (next.config.ts), not needed here.
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The official node image already ships an unprivileged `node` user (uid 1000).
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

USER node
EXPOSE 3000

# No default HEALTHCHECK -- docker-compose.yml defines it (a plain HTTP probe;
# the dashboard has no /health route of its own, that is the API's concern).
CMD ["node", "server.js"]
