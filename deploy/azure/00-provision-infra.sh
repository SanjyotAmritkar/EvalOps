#!/usr/bin/env bash
# One-time Azure infrastructure provisioning (Phase 10, CP 10.5).
#
# Creates: resource group, ACR, a user-assigned managed identity with AcrPull
# on that registry, a Log Analytics workspace + Container Apps environment,
# a PostgreSQL Flexible Server, and Redis running as a Container App (internal
# ingress only -- see README.md for why this, not Azure Cache for Redis).
#
# Run once, by a human, from a machine with `az login` already done. Safe to
# re-run: every step checks whether its resource already exists first. Never
# run by CI. Does NOT create the application Container Apps or the migration
# job -- that is 01-provision-apps.sh, after the first image exists in ACR.
#
# Usage: ./00-provision-infra.sh   (after: cp config.env.example config.env
# and filling it in)

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
require_cmd openssl
load_config
for v in AZURE_SUBSCRIPTION_ID AZURE_LOCATION RESOURCE_GROUP ACR_NAME IDENTITY_NAME \
  CONTAINERAPPS_ENV LOG_ANALYTICS_WORKSPACE POSTGRES_SERVER_NAME POSTGRES_ADMIN_USER \
  POSTGRES_DB_NAME POSTGRES_SKU POSTGRES_STORAGE_GB REDIS_APP_NAME; do
  require_var "$v"
done

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

mkdir -p ./.secrets
chmod 700 ./.secrets

log "Resource group: $RESOURCE_GROUP"
az group create --name "$RESOURCE_GROUP" --location "$AZURE_LOCATION" >/dev/null

log "Container registry: $ACR_NAME (no admin user -- pulled via managed identity only)"
if ! resource_exists az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP"; then
  az acr create --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --sku Basic --admin-enabled false >/dev/null
else
  log "  already exists, skipping"
fi
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

log "Managed identity: $IDENTITY_NAME"
if ! resource_exists az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP"; then
  az identity create --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" >/dev/null
else
  log "  already exists, skipping"
fi
IDENTITY_PRINCIPAL_ID=$(az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv)

log "Granting AcrPull on $ACR_NAME to $IDENTITY_NAME"
az role assignment create --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID" >/dev/null 2>&1 \
  || log "  role assignment already present, skipping"

log "Log Analytics workspace: $LOG_ANALYTICS_WORKSPACE"
if ! resource_exists az monitor log-analytics workspace show \
  --workspace-name "$LOG_ANALYTICS_WORKSPACE" --resource-group "$RESOURCE_GROUP"; then
  az monitor log-analytics workspace create --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
    --resource-group "$RESOURCE_GROUP" --location "$AZURE_LOCATION" >/dev/null
else
  log "  already exists, skipping"
fi
LOG_ANALYTICS_CLIENT_ID=$(az monitor log-analytics workspace show \
  --workspace-name "$LOG_ANALYTICS_WORKSPACE" --resource-group "$RESOURCE_GROUP" \
  --query customerId -o tsv)
LOG_ANALYTICS_CLIENT_SECRET=$(az monitor log-analytics workspace get-shared-keys \
  --workspace-name "$LOG_ANALYTICS_WORKSPACE" --resource-group "$RESOURCE_GROUP" \
  --query primarySharedKey -o tsv)

log "Container Apps environment: $CONTAINERAPPS_ENV"
if ! resource_exists az containerapp env show --name "$CONTAINERAPPS_ENV" \
  --resource-group "$RESOURCE_GROUP"; then
  az containerapp env create --name "$CONTAINERAPPS_ENV" --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --logs-workspace-id "$LOG_ANALYTICS_CLIENT_ID" \
    --logs-workspace-key "$LOG_ANALYTICS_CLIENT_SECRET" >/dev/null
else
  log "  already exists, skipping"
fi

log "PostgreSQL Flexible Server: $POSTGRES_SERVER_NAME"
if [ ! -f ./.secrets/database-url ]; then
  if resource_exists az postgres flexible-server show --name "$POSTGRES_SERVER_NAME" \
    --resource-group "$RESOURCE_GROUP"; then
    die "Postgres server '$POSTGRES_SERVER_NAME' already exists but ./.secrets/database-url is" \
      " missing -- the admin password was not recorded by this script. Reset it manually" \
      " (az postgres flexible-server update --name ... --admin-password ...) and write the" \
      " resulting DATABASE_URL to ./.secrets/database-url yourself."
  fi
  PG_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/\n')
  # Public access, Azure-services-only (no VNet in this portfolio topology --
  # see README's "PostgreSQL public access" tradeoff). The migration job and
  # api/worker reach it as Azure services; nothing else is allowlisted.
  az postgres flexible-server create \
    --name "$POSTGRES_SERVER_NAME" --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --admin-user "$POSTGRES_ADMIN_USER" --admin-password "$PG_PASSWORD" \
    --database-name "$POSTGRES_DB_NAME" \
    --sku-name "$POSTGRES_SKU" --tier Burstable \
    --storage-size "$POSTGRES_STORAGE_GB" \
    --public-access 0.0.0.0 \
    --yes >/dev/null
  printf 'postgresql+psycopg://%s:%s@%s.postgres.database.azure.com:5432/%s?sslmode=require\n' \
    "$POSTGRES_ADMIN_USER" "$PG_PASSWORD" "$POSTGRES_SERVER_NAME" "$POSTGRES_DB_NAME" \
    >./.secrets/database-url
  chmod 600 ./.secrets/database-url
  unset PG_PASSWORD
  log "  created; connection string written to ./.secrets/database-url (not printed, not committed)"
else
  log "  ./.secrets/database-url already present, assuming the server exists -- skipping"
fi

log "Redis broker (Container App, internal ingress, no persistence): $REDIS_APP_NAME"
if ! resource_exists az containerapp show --name "$REDIS_APP_NAME" --resource-group "$RESOURCE_GROUP"; then
  az containerapp create \
    --name "$REDIS_APP_NAME" --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "docker.io/library/redis:7-alpine" \
    --command "redis-server" --args "--save" "" "--appendonly" "no" \
    --ingress internal --target-port 6379 --transport tcp \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.25 --memory 0.5Gi >/dev/null
else
  log "  already exists, skipping"
fi
REDIS_FQDN=$(az containerapp show --name "$REDIS_APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)
printf 'redis://%s:6379/0\n' "$REDIS_FQDN" >./.secrets/redis-broker-url
chmod 600 ./.secrets/redis-broker-url

log "Infra provisioning done."
log "Next: run ./01-provision-apps.sh --image-tag <tag> once an image exists in $ACR_NAME."
