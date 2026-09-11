# EvalOps on Azure (Phase 10, CP 10.5)

Reproducible scripts + a GitHub Actions workflow for the Azure topology that
was already proven manually:

```
                         ┌─────────────────────────────┐
 browser ──────────────► │ dashboard (Container App)    │
                         │  Next.js standalone,          │
                         │  server-side /api/* proxy     │
                         └──────────────┬───────────────┘
                                        │ HTTPS + Authorization: Bearer <key>
                                        ▼
                         ┌─────────────────────────────┐
 curl / direct client ─► │ api (Container App)          │
                         │  FastAPI, EVALOPS_API_KEY     │
                         └───┬───────────────────┬───────┘
                             │                   │
                             ▼                   ▼
                 ┌───────────────────┐   ┌───────────────────┐
                 │ PostgreSQL         │   │ redis (Container   │
                 │ Flexible Server    │   │ App, internal-only,│
                 │ -- source of truth │   │ TCP ingress)        │
                 └─────────▲──────────┘   └─────────▲──────────┘
                           │                          │
                           └──────────┬───────────────┘
                                      │
                         ┌────────────┴────────────┐
                         │ worker (Container App)    │
                         │  Celery, no ingress        │
                         └────────────────────────────┘

  migrate (Container Apps Job, Manual trigger, "alembic upgrade head")
  runs before api/worker start serving on every deploy.
```

Same images, same evaluation/gate/persistence code as
[docker-compose.yml](../../docker-compose.yml) (CP 10.4) -- this is a
deployment target, not a different architecture. See
`docs/ARCHITECTURE.md` §7.11 for how the two topologies relate.

**Everything here is a template.** No script in this directory has been run
against a real Azure subscription by Claude -- these are reviewed and run by
a human. Nothing here contains a real resource name, subscription ID, or
secret; `config.env` (real names) and `.secrets/` (generated passwords/keys)
are both git-ignored and must never be committed.

**Already have these Container Apps running (created by hand)?** Skip to
["Adopt an existing deployment"](#adopt-an-existing-already-provisioned-deployment)
below -- do not run `00-provision-infra.sh` / `01-provision-apps.sh` against
resources they didn't create.

## One-time setup (fresh Azure subscription only)

Prerequisites: `az login` already done, an Azure subscription, `bash`,
`openssl`, `curl`, and (for the very first image) `docker` with `buildx`.

```bash
cd deploy/azure
cp config.env.example config.env   # then fill in real names for your subscription
```

1. **`./00-provision-infra.sh`** -- resource group, ACR (no admin user),
   a user-assigned managed identity with `AcrPull` (Container Apps use this to
   pull images -- no stored registry credential), a Log Analytics workspace +
   Container Apps environment, a PostgreSQL Flexible Server (password
   generated once, written only to `./.secrets/database-url`, never printed),
   and Redis running as a Container App (`./.secrets/redis-broker-url`).

2. **Build and push one image manually**, so step 3 has something to deploy
   (every deploy after this one is what `.github/workflows/deploy-azure.yml`
   does automatically):

   ```bash
   az acr login --name <ACR_NAME>
   TAG=bootstrap
   docker buildx build --platform linux/amd64 --push \
     -t <ACR_NAME>.azurecr.io/evalops-backend:$TAG .
   docker buildx build --platform linux/amd64 --push \
     -t <ACR_NAME>.azurecr.io/evalops-dashboard:$TAG ./dashboard
   ```

3. **`./01-provision-apps.sh --image-tag bootstrap`** -- creates the
   `migrate` Container Apps Job and the `api`/`worker`/`dashboard` Container
   Apps, wiring `DATABASE_URL`/`CELERY_BROKER_URL`/`EVALOPS_API_KEY` in as
   Container Apps **secrets** (never a plain env var), generating
   `EVALOPS_API_KEY` once into `./.secrets/api-key` if it doesn't already
   exist. Prints the dashboard and API URLs at the end.

4. **`./03-github-oidc.sh`** -- a *separate* identity for GitHub Actions
   (`AcrPush` + `Container Apps Contributor` + `Container Apps Jobs
   Contributor`, scoped only to this resource group), trusted via OIDC
   federated credential for this exact repo's `production` GitHub Environment
   -- no Azure password or service-principal secret is ever stored in GitHub.
   Prints `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`.

## Adopt an existing (already-provisioned) deployment

If your Container Apps already exist -- created by hand, or before these
scripts existed -- **do not run `00-provision-infra.sh` or
`01-provision-apps.sh` against them.** Both assume a from-scratch setup and
either error on (infra) or skip past (apps) anything already present, but
neither is the intended path for infrastructure you did not provision with
them, and re-running either is not a supported way to "adjust" a live
deployment.

Instead:

```bash
cd deploy/azure
cp config.env.example config.env   # fill in RESOURCE_GROUP, API_APP_NAME,
                                    # WORKER_APP_NAME, DASHBOARD_APP_NAME to
                                    # match your real, already-existing apps
./04-adopt-existing.sh
```

`04-adopt-existing.sh` verifies the three apps already exist (refuses to run
if any is missing -- it never creates one), then **only**: generates (or
reuses) one `EVALOPS_API_KEY`, sets it as a Container Apps secret named
`evalops-api-key` on **api** and **dashboard**, points each app's
`EVALOPS_API_KEY` env var at that secret, and sets `EVALOPS_ENV=production`
on **api** and **worker**. It never touches the resource group, ACR, the
managed identity, the Container Apps environment, PostgreSQL, Redis, ingress,
the migration job, or any other existing env var/secret -- `DATABASE_URL`,
`CELERY_BROKER_URL`, the dashboard's existing `API_PROXY_TARGET`, and any
provider key are left exactly as they are (Container Apps secret/env-var
updates are additive: naming one never removes another). Safe to re-run.

After this, `./02-deploy.sh --image-tag <tag>` (and the GitHub Actions
workflow) work against your existing deployment exactly as documented below.

## GitHub configuration (manual, one time)

Repo Settings → **Environments** → create `production`:

- Add a **required reviewers** protection rule -- this, not the
  `workflow_dispatch` trigger, is the actual deployment gate.
- Add these as Environment **variables** (Settings → Environments →
  production → Variables -- not secrets; none of these are secret):

  | Variable | Value |
  |---|---|
  | `AZURE_CLIENT_ID` | printed by `03-github-oidc.sh` |
  | `AZURE_TENANT_ID` | printed by `03-github-oidc.sh` |
  | `AZURE_SUBSCRIPTION_ID` | your subscription id |
  | `AZURE_LOCATION` | e.g. `eastus` |
  | `AZURE_RESOURCE_GROUP` | your `RESOURCE_GROUP` from `config.env` |
  | `ACR_NAME` | your `ACR_NAME` from `config.env` |
  | `MIGRATE_JOB_NAME` | your `MIGRATE_JOB_NAME` |
  | `API_APP_NAME` | your `API_APP_NAME` |
  | `WORKER_APP_NAME` | your `WORKER_APP_NAME` |
  | `DASHBOARD_APP_NAME` | your `DASHBOARD_APP_NAME` |

No Azure credential of any kind is a GitHub *secret* -- OIDC needs none, and
every value above is a name, not a password.

## Deploying

**Actions tab → "Deploy to Azure (production)" → Run workflow.**

- **Leave `image_tag` blank** (the normal path) to build and deploy the
  checked-out commit: runs the same checks CI runs → builds + pushes
  linux/amd64 images tagged with the commit SHA (and `:latest`) → runs the
  migration job and **stops here if it fails** → rolls
  `api`/`worker`/`dashboard` forward to that SHA.
- **Set `image_tag`** to an existing ACR tag (e.g. a previous commit SHA) to
  redeploy/roll back **without rebuilding**: the build step is skipped
  entirely, the workflow verifies that exact tag already exists in ACR
  (refusing to proceed otherwise), and deploys it as-is -- an immutable tag
  is never overwritten with whatever happens to be checked out.

Either way, `EVALOPS_REVISION` is set to the full deployed tag/SHA, and the
Container Apps **revision suffix** is `sha-<12-char-tag-prefix>-<unix
timestamp>` -- unique per deploy run even when redeploying the identical tag
twice, so it never collides with a still-existing revision name. Finishes
with a bounded post-deploy check: API `/health` + `/ready`, the dashboard's
root, and `https://<dashboard-fqdn>/api/projects` with **no** credential
supplied by the workflow -- a 2xx there proves the dashboard's server-side
proxy injected its own `EVALOPS_API_KEY` correctly, without the runner ever
holding that key.

**Manual redeploy / rollback**, from a machine with `az login` and
`config.env` filled in:

```bash
cd deploy/azure
./02-deploy.sh --image-tag <sha-already-in-acr>
```

## Runtime configuration

Set once by `01-provision-apps.sh` (fresh deployment) or `04-adopt-existing.sh`
(already-existing deployment) as Container Apps secrets/env vars (never
edited directly in the Portal without also updating `config.env`'s intent):

`DATABASE_URL`, `CELERY_BROKER_URL`, `EVALOPS_API_KEY` -- secrets.
`EVALOPS_ENV=production`, `EVALOPS_REVISION` (kept at the deployed SHA by
every `02-deploy.sh` run), `EVALOPS_LOG_FORMAT=json`, `EVALOPS_LOG_LEVEL`,
`EVALOPS_REQUIRE_REDIS=true`, `API_PROXY_TARGET` (dashboard, set to the API's
HTTPS FQDN) -- plain env vars. Provider keys (`OPENAI_API_KEY` /
`ANTHROPIC_API_KEY`) are not set by these scripts at all -- add them the same
way (`az containerapp secret set` + `--set-env-vars ...=secretref:...`) only
if a deployed `SystemVersion` actually targets a hosted provider; the
deterministic Mock path needs none.

## Tradeoffs, honestly

- **Redis is a Container App running `redis:7-alpine`, not Azure Cache for
  Redis.** This is the portfolio/free-tier-compatible choice: no persistence,
  a single replica, and a worker/broker restart loses whatever was queued but
  not yet delivered -- consistent with (not an added risk beyond) the
  at-most-once task delivery `src/evalops/worker/celery_app.py` already
  documents. It is not presented as the ideal production-managed-Redis
  architecture; swapping in Azure Cache for Redis later is a `CELERY_BROKER_URL`
  change, nothing else.
- **PostgreSQL Flexible Server uses `--public-access 0.0.0.0`** (Azure
  services only, not the public internet at large) rather than a private
  VNet + private endpoint, because this topology has no VNet. The migration
  Job and `api`/`worker` reach it as Azure services; nothing else is
  allowlisted. A VNet-integrated Container Apps environment + private Postgres
  access is the natural next step if this ever needs to be more than a
  portfolio deployment.
- **No custom domain / certificate management** -- Container Apps' own
  `*.azurecontainerapps.io` FQDN and managed TLS are used as-is.
- **No autoscaling beyond `--min-replicas`/`--max-replicas`** set once at
  creation; revisit if real load ever demands it.
- Still no OAuth/user accounts/RBAC, no Kubernetes, no service mesh, no
  Prometheus/Grafana/OpenTelemetry -- unchanged from the rest of Phase 10 (see
  `docs/ARCHITECTURE.md`).
