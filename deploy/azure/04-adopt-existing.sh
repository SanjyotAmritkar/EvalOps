#!/usr/bin/env bash
# Adopt an ALREADY-EXISTING, manually-provisioned Azure deployment into the
# CP 10.5 security model (Phase 10, CP 10.5 follow-up).
#
# For a deployment whose Container Apps were created by hand (or by a prior,
# separate process) before these scripts existed. This is deliberately NOT
# 00-provision-infra.sh / 01-provision-apps.sh and must never be confused with
# them: it creates nothing, and it never re-runs infra provisioning.
#
# It ONLY:
#   - verifies the api/worker/dashboard Container Apps you named in
#     config.env already exist (fails loudly, changes nothing, if any is
#     missing -- it will not create one)
#   - generates EVALOPS_API_KEY once (or reuses ./.secrets/api-key if you
#     already have one) and sets it as a Container Apps *secret* named
#     evalops-api-key on the api and dashboard apps only
#   - points api's (and dashboard's) EVALOPS_API_KEY env var at that secret
#   - sets EVALOPS_ENV=production on api and worker
#
# It NEVER touches: the resource group, ACR, the managed identity, the
# Container Apps environment, PostgreSQL, Redis, ingress configuration, the
# migration job, or any existing env var/secret other than the two named
# above -- in particular DATABASE_URL, CELERY_BROKER_URL, API_PROXY_TARGET,
# and any provider key are left exactly as they already are (Container Apps'
# secret/env-var update is additive: naming one secret or env var never
# removes another).
#
# Usage: ./04-adopt-existing.sh
# Safe to re-run: every step is an idempotent upsert.

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
require_cmd openssl
load_config
for v in RESOURCE_GROUP API_APP_NAME WORKER_APP_NAME DASHBOARD_APP_NAME; do
  require_var "$v"
done
if [ -n "${AZURE_SUBSCRIPTION_ID:-}" ]; then
  az account set --subscription "$AZURE_SUBSCRIPTION_ID"
fi

for app in "$API_APP_NAME" "$WORKER_APP_NAME" "$DASHBOARD_APP_NAME"; do
  resource_exists az containerapp show --name "$app" --resource-group "$RESOURCE_GROUP" \
    || die "Container App '$app' was not found in resource group '$RESOURCE_GROUP'." \
      " This script only configures an EXISTING deployment -- it does not create one." \
      " Check config.env against your real Azure resource names."
done
log "Confirmed api/worker/dashboard already exist -- adopting, not (re)creating, anything."

mkdir -p ./.secrets && chmod 700 ./.secrets
if [ ! -f ./.secrets/api-key ]; then
  openssl rand -hex 32 >./.secrets/api-key
  chmod 600 ./.secrets/api-key
  log "Generated a new EVALOPS_API_KEY in ./.secrets/api-key (not printed, not committed)."
else
  log "Reusing the existing key in ./.secrets/api-key."
fi
EVALOPS_API_KEY=$(cat ./.secrets/api-key)

log "API app ($API_APP_NAME): setting evalops-api-key secret, EVALOPS_API_KEY, EVALOPS_ENV=production"
az containerapp secret set --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --secrets "evalops-api-key=${EVALOPS_API_KEY}" >/dev/null
az containerapp update --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "EVALOPS_API_KEY=secretref:evalops-api-key" "EVALOPS_ENV=production" >/dev/null

log "Worker app ($WORKER_APP_NAME): setting EVALOPS_ENV=production (no API key -- the worker never calls the HTTP API)"
az containerapp update --name "$WORKER_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "EVALOPS_ENV=production" >/dev/null

log "Dashboard app ($DASHBOARD_APP_NAME): setting the SAME evalops-api-key secret + EVALOPS_API_KEY (API_PROXY_TARGET left untouched)"
az containerapp secret set --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --secrets "evalops-api-key=${EVALOPS_API_KEY}" >/dev/null
az containerapp update --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "EVALOPS_API_KEY=secretref:evalops-api-key" >/dev/null

log "Done. api and dashboard share one EVALOPS_API_KEY; DATABASE_URL, CELERY_BROKER_URL,"
log "API_PROXY_TARGET, and any provider key were not touched."
log "Verify with: curl -fsS https://<api-fqdn>/projects  # -> 401 (no header)"
log "             curl -fsS https://<dashboard-fqdn>/api/projects  # -> 200 (proxy injects the key)"
log "Next deploy (./02-deploy.sh --image-tag <tag>) will set EVALOPS_REVISION as usual."
