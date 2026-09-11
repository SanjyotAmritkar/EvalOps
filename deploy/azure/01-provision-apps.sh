#!/usr/bin/env bash
# One-time creation of the application Container Apps + migration Job
# (Phase 10, CP 10.5). Run once, by a human, after 00-provision-infra.sh and
# after at least one image tag exists in ACR (build/push it yourself once --
# see README.md -- or let the first CI deploy run 02-deploy.sh instead, which
# also creates these on first use... except a Job/App must already exist for
# `containerapp update`/`job update` to apply to, which is exactly what this
# script does). Safe to re-run: every resource is created only if missing.
#
# Usage: ./01-provision-apps.sh --image-tag <tag>

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
require_cmd openssl
load_config
for v in RESOURCE_GROUP ACR_NAME IDENTITY_NAME CONTAINERAPPS_ENV \
  MIGRATE_JOB_NAME API_APP_NAME WORKER_APP_NAME DASHBOARD_APP_NAME CELERY_CONCURRENCY; do
  require_var "$v"
done
if [ -n "${AZURE_SUBSCRIPTION_ID:-}" ]; then
  az account set --subscription "$AZURE_SUBSCRIPTION_ID"
fi

IMAGE_TAG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --image-tag) IMAGE_TAG="$2"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ -n "$IMAGE_TAG" ] || die "usage: $0 --image-tag <tag>"

[ -f ./.secrets/database-url ] || die "./.secrets/database-url missing -- run 00-provision-infra.sh first"
[ -f ./.secrets/redis-broker-url ] || die "./.secrets/redis-broker-url missing -- run 00-provision-infra.sh first"
DATABASE_URL=$(cat ./.secrets/database-url)
CELERY_BROKER_URL=$(cat ./.secrets/redis-broker-url)

if [ ! -f ./.secrets/api-key ]; then
  openssl rand -hex 32 >./.secrets/api-key
  chmod 600 ./.secrets/api-key
  log "Generated a new EVALOPS_API_KEY in ./.secrets/api-key (not printed, not committed)."
fi
EVALOPS_API_KEY=$(cat ./.secrets/api-key)

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
IDENTITY_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

BACKEND_IMAGE="${ACR_LOGIN_SERVER}/evalops-backend:${IMAGE_TAG}"
DASHBOARD_IMAGE="${ACR_LOGIN_SERVER}/evalops-dashboard:${IMAGE_TAG}"

# --- migration job --------------------------------------------------------
log "Migration job: $MIGRATE_JOB_NAME"
if ! resource_exists az containerapp job show --name "$MIGRATE_JOB_NAME" --resource-group "$RESOURCE_GROUP"; then
  az containerapp job create \
    --name "$MIGRATE_JOB_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --trigger-type Manual --replica-timeout 900 --replica-retry-limit 0 --parallelism 1 \
    --replica-completion-count 1 \
    --image "$BACKEND_IMAGE" \
    --registry-server "$ACR_LOGIN_SERVER" --registry-identity "$IDENTITY_ID" \
    --mi-user-assigned "$IDENTITY_ID" \
    --command "alembic" --args "upgrade" "head" \
    --cpu 0.5 --memory 1.0Gi \
    --secrets "database-url=${DATABASE_URL}" \
    --env-vars "DATABASE_URL=secretref:database-url" "EVALOPS_ENV=production" \
      "EVALOPS_LOG_FORMAT=json" "EVALOPS_REVISION=${IMAGE_TAG}" >/dev/null
else
  log "  already exists (02-deploy.sh updates its image on every deploy) -- skipping"
fi

# --- api -------------------------------------------------------------------
log "API app: $API_APP_NAME"
if ! resource_exists az containerapp show --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP"; then
  az containerapp create \
    --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$BACKEND_IMAGE" \
    --registry-server "$ACR_LOGIN_SERVER" --registry-identity "$IDENTITY_ID" \
    --user-assigned "$IDENTITY_ID" \
    --ingress external --target-port 8000 \
    --min-replicas 1 --max-replicas 2 --cpu 0.5 --memory 1.0Gi \
    --command "uvicorn" \
    --args "evalops.api.main:app" "--host" "0.0.0.0" "--port" "8000" \
      "--timeout-graceful-shutdown" "10" \
    --secrets "database-url=${DATABASE_URL}" "celery-broker-url=${CELERY_BROKER_URL}" \
      "evalops-api-key=${EVALOPS_API_KEY}" \
    --env-vars "DATABASE_URL=secretref:database-url" "CELERY_BROKER_URL=secretref:celery-broker-url" \
      "EVALOPS_API_KEY=secretref:evalops-api-key" "EVALOPS_ENV=production" \
      "EVALOPS_REVISION=${IMAGE_TAG}" "EVALOPS_LOG_FORMAT=json" "EVALOPS_LOG_LEVEL=INFO" \
      "EVALOPS_REQUIRE_REDIS=true" >/dev/null
else
  log "  already exists -- skipping (02-deploy.sh handles redeploys)"
fi
API_FQDN=$(az containerapp show --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)
log "  API FQDN: https://${API_FQDN}"

# --- worker ------------------------------------------------------------
log "Worker app: $WORKER_APP_NAME"
if ! resource_exists az containerapp show --name "$WORKER_APP_NAME" --resource-group "$RESOURCE_GROUP"; then
  az containerapp create \
    --name "$WORKER_APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$BACKEND_IMAGE" \
    --registry-server "$ACR_LOGIN_SERVER" --registry-identity "$IDENTITY_ID" \
    --user-assigned "$IDENTITY_ID" \
    --min-replicas 1 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
    --command "celery" \
    --args "-A" "evalops.worker.celery_app:celery_app" "worker" "--loglevel=info" \
      "--concurrency=${CELERY_CONCURRENCY}" \
    --secrets "database-url=${DATABASE_URL}" "celery-broker-url=${CELERY_BROKER_URL}" \
    --env-vars "DATABASE_URL=secretref:database-url" "CELERY_BROKER_URL=secretref:celery-broker-url" \
      "EVALOPS_ENV=production" "EVALOPS_REVISION=${IMAGE_TAG}" "EVALOPS_LOG_FORMAT=json" \
      "EVALOPS_LOG_LEVEL=INFO" >/dev/null
else
  log "  already exists -- skipping (02-deploy.sh handles redeploys)"
fi

# --- dashboard ---------------------------------------------------------
log "Dashboard app: $DASHBOARD_APP_NAME"
if ! resource_exists az containerapp show --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP"; then
  az containerapp create \
    --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$DASHBOARD_IMAGE" \
    --registry-server "$ACR_LOGIN_SERVER" --registry-identity "$IDENTITY_ID" \
    --user-assigned "$IDENTITY_ID" \
    --ingress external --target-port 3000 \
    --min-replicas 1 --max-replicas 2 --cpu 0.25 --memory 0.5Gi \
    --secrets "evalops-api-key=${EVALOPS_API_KEY}" \
    --env-vars "API_PROXY_TARGET=https://${API_FQDN}" "EVALOPS_API_KEY=secretref:evalops-api-key" \
      >/dev/null
else
  log "  already exists -- skipping (02-deploy.sh handles redeploys)"
fi
DASHBOARD_FQDN=$(az containerapp show --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

log "App provisioning done."
log "  Dashboard: https://${DASHBOARD_FQDN}"
log "  API:       https://${API_FQDN}"
log "Next: run ./02-deploy.sh --image-tag <tag> to migrate + roll out every future deploy."
