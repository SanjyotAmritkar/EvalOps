#!/usr/bin/env bash
# Repeatable deploy (Phase 10, CP 10.5): update the migration job to the new
# image, run it and wait for it to succeed, then roll api/worker/dashboard
# forward to the same immutable tag. This is what
# .github/workflows/deploy-azure.yml calls; a human can also run it directly
# for a manual redeploy. Requires 00-provision-infra.sh and
# 01-provision-apps.sh to have already run once.
#
# Usage: ./02-deploy.sh --image-tag <immutable-tag, e.g. a git commit SHA>
#
# Fails (non-zero exit) if the migration does not succeed -- api/worker/
# dashboard are never rolled forward on top of a failed or unknown-state
# migration.

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
load_config
for v in RESOURCE_GROUP ACR_NAME MIGRATE_JOB_NAME API_APP_NAME WORKER_APP_NAME DASHBOARD_APP_NAME; do
  require_var "$v"
done

# In CI, azure/login@v2 already selected the subscription; this is a no-op
# there and a convenience when run by hand against a different default one.
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

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"
BACKEND_IMAGE="${ACR_LOGIN_SERVER}/evalops-backend:${IMAGE_TAG}"
DASHBOARD_IMAGE="${ACR_LOGIN_SERVER}/evalops-dashboard:${IMAGE_TAG}"

# Container Apps revision suffixes must be <=64 chars, lowercase alphanumeric/
# '-'. EVALOPS_REVISION below stays exactly IMAGE_TAG (the immutable SHA/tag);
# the *suffix* additionally carries a deploy timestamp so redeploying or
# rolling back to the *same* tag twice never collides with a still-existing
# revision name (Container Apps rejects a duplicate revision suffix outright).
SAFE_TAG=$(printf '%s' "${IMAGE_TAG:0:12}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-')
REVISION_SUFFIX="sha-${SAFE_TAG}-$(date -u +%s)"

# --- 1. migrate: update image, run, wait, fail loudly on anything but success ---
log "Updating migration job image to ${BACKEND_IMAGE}"
az containerapp job update --name "$MIGRATE_JOB_NAME" --resource-group "$RESOURCE_GROUP" \
  --image "$BACKEND_IMAGE" >/dev/null

log "Starting migration run"
EXECUTION_NAME=$(az containerapp job start --name "$MIGRATE_JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" --query name -o tsv)
log "  execution: ${EXECUTION_NAME}"

STATUS="Running"
for _ in $(seq 1 60); do  # up to ~10 minutes (60 * 10s)
  STATUS=$(az containerapp job execution show --name "$MIGRATE_JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" --job-execution-name "$EXECUTION_NAME" \
    --query properties.status -o tsv)
  case "$STATUS" in
    Succeeded) break ;;
    Failed|"") die "migration execution ${EXECUTION_NAME} ended with status '${STATUS}' -- aborting deploy, api/worker/dashboard are NOT rolled forward" ;;
    *) sleep 10 ;;
  esac
done
[ "$STATUS" = "Succeeded" ] || die "migration execution ${EXECUTION_NAME} did not succeed within the wait budget (last status: ${STATUS})"
log "Migration succeeded."

# --- 2. roll api/worker/dashboard forward to the same immutable tag ---
log "Updating API app -> ${BACKEND_IMAGE} (${REVISION_SUFFIX})"
az containerapp update --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --image "$BACKEND_IMAGE" --revision-suffix "$REVISION_SUFFIX" \
  --set-env-vars "EVALOPS_REVISION=${IMAGE_TAG}" >/dev/null

log "Updating worker app -> ${BACKEND_IMAGE} (${REVISION_SUFFIX})"
az containerapp update --name "$WORKER_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --image "$BACKEND_IMAGE" --revision-suffix "$REVISION_SUFFIX" \
  --set-env-vars "EVALOPS_REVISION=${IMAGE_TAG}" >/dev/null

log "Updating dashboard app -> ${DASHBOARD_IMAGE} (${REVISION_SUFFIX})"
az containerapp update --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --image "$DASHBOARD_IMAGE" --revision-suffix "$REVISION_SUFFIX" >/dev/null

# --- 3. bounded post-deploy smoke check -----------------------------------
API_FQDN=$(az containerapp show --name "$API_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)
DASHBOARD_FQDN=$(az containerapp show --name "$DASHBOARD_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)

log "Smoke check: https://${API_FQDN}/health and /ready"
ready=0
for _ in $(seq 1 20); do  # up to ~2 minutes
  if curl -fsS "https://${API_FQDN}/health" >/dev/null 2>&1 \
    && curl -fsS "https://${API_FQDN}/ready" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 6
done
[ "$ready" = "1" ] || die "API did not report healthy/ready at https://${API_FQDN} within the wait budget"
log "  API is healthy and ready."

log "Smoke check: https://${DASHBOARD_FQDN}/"
if ! curl -fsS -o /dev/null "https://${DASHBOARD_FQDN}/"; then
  die "dashboard did not respond at https://${DASHBOARD_FQDN}"
fi
log "  Dashboard responded."

# Proves the real end-to-end auth path -- dashboard's server-side proxy
# injects its own EVALOPS_API_KEY -- without this script (or the caller, e.g.
# the GitHub Actions runner) ever holding or sending that key itself. /projects
# is an existing, safe, read-only GET; a 401 here means the dashboard's own
# EVALOPS_API_KEY does not match the API's, even if both apps are "up".
log "Smoke check: https://${DASHBOARD_FQDN}/api/projects (dashboard -> server-side API-key injection -> API)"
if ! curl -fsS -o /dev/null "https://${DASHBOARD_FQDN}/api/projects"; then
  die "dashboard could not reach an authenticated API route via its own proxy" \
    " (https://${DASHBOARD_FQDN}/api/projects) -- check that EVALOPS_API_KEY matches" \
    " between the api and dashboard Container Apps"
fi
log "  Dashboard authenticated to the API server-side."

log "Deploy complete: revision ${REVISION_SUFFIX} (${IMAGE_TAG})"
