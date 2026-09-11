#!/usr/bin/env bash
# One-time setup of a *separate* identity for GitHub Actions deployment
# (Phase 10, CP 10.5): OIDC/federated-credential login, no stored Azure
# password or service-principal secret anywhere in GitHub.
#
# Deliberately not the same identity 00-provision-infra.sh created for the
# Container Apps to pull images at runtime (AcrPull only) -- this one needs to
# *push* images and *manage* Container Apps/Jobs, a materially larger
# privilege set that should not sit on the always-on runtime identity.
#
# After running this, put GITHUB_DEPLOY_CLIENT_ID (printed at the end),
# AZURE_TENANT_ID, and AZURE_SUBSCRIPTION_ID into the repo's "production"
# GitHub Environment as *variables* (not secrets -- a client ID is not a
# secret; OIDC needs no client secret at all). See README.md.
#
# Usage: ./03-github-oidc.sh

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
load_config
for v in RESOURCE_GROUP ACR_NAME AZURE_SUBSCRIPTION_ID GITHUB_ORG GITHUB_REPO \
  GITHUB_DEPLOY_IDENTITY_NAME; do
  require_var "$v"
done

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
TENANT_ID=$(az account show --query tenantId -o tsv)
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
RG_ID=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)

log "Deploy identity: $GITHUB_DEPLOY_IDENTITY_NAME"
if ! resource_exists az identity show --name "$GITHUB_DEPLOY_IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP"; then
  az identity create --name "$GITHUB_DEPLOY_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" >/dev/null
else
  log "  already exists, skipping"
fi
DEPLOY_PRINCIPAL_ID=$(az identity show --name "$GITHUB_DEPLOY_IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" --query principalId -o tsv)
DEPLOY_CLIENT_ID=$(az identity show --name "$GITHUB_DEPLOY_IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" --query clientId -o tsv)

log "Granting AcrPush on $ACR_NAME"
az role assignment create --assignee-object-id "$DEPLOY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role AcrPush --scope "$ACR_ID" >/dev/null 2>&1 \
  || log "  already present, skipping"

log "Granting Container Apps Contributor + Container Apps Jobs Contributor on $RESOURCE_GROUP"
az role assignment create --assignee-object-id "$DEPLOY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role "Container Apps Contributor" --scope "$RG_ID" \
  >/dev/null 2>&1 || log "  Container Apps Contributor already present, skipping"
az role assignment create --assignee-object-id "$DEPLOY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal --role "Container Apps Jobs Contributor" --scope "$RG_ID" \
  >/dev/null 2>&1 || log "  Container Apps Jobs Contributor already present, skipping"

# Trust only workflow runs executing under the repo's "production" GitHub
# Environment -- combined with that Environment's required-reviewer
# protection rule, this is the actual deployment gate, not the workflow_dispatch
# trigger alone.
log "Federated credential for repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:production"
if ! resource_exists az identity federated-credential show \
  --name github-production --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP"; then
  az identity federated-credential create \
    --name github-production \
    --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
    --issuer "https://token.actions.githubusercontent.com" \
    --subject "repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:production" \
    --audiences "api://AzureADTokenExchange" >/dev/null
else
  log "  already exists, skipping"
fi

log "Done. Add these to the GitHub repo's 'production' Environment as VARIABLES (not secrets):"
log "  AZURE_CLIENT_ID       = ${DEPLOY_CLIENT_ID}"
log "  AZURE_TENANT_ID       = ${TENANT_ID}"
log "  AZURE_SUBSCRIPTION_ID = ${AZURE_SUBSCRIPTION_ID}"
log "None of these are secrets -- OIDC needs no client secret. See README.md."
