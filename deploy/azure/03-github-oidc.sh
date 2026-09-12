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
# --- OIDC subject: immutable IDs, not just names -------------------------
# GitHub's OIDC subject for an Environment-scoped run is
#   repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<environment>
# The `@<owner_id>`/`@<repo_id>` suffixes are GitHub's own immutable numeric
# IDs -- present once a repo has ever been renamed or transferred, which
# GitHub then requires. Hard-coding just `repo:<owner>/<repo>:environment:...`
# (no IDs) produces a subject that does not match what GitHub actually sends,
# and the federated credential silently never matches. GITHUB_ORG/GITHUB_REPO
# stay the human-facing config inputs; this script resolves the numeric IDs
# from the GitHub REST API (unauthenticated works for a public repo; set
# GITHUB_TOKEN to a token with at least public read access if the repo is
# private or you hit anonymous rate limits) and fails clearly if it cannot.
#
# Usage: ./03-github-oidc.sh

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
source ./lib.sh

require_cmd az
require_cmd curl
require_cmd python3
load_config
for v in RESOURCE_GROUP ACR_NAME AZURE_SUBSCRIPTION_ID GITHUB_ORG GITHUB_REPO \
  GITHUB_DEPLOY_IDENTITY_NAME; do
  require_var "$v"
done

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
TENANT_ID=$(az account show --query tenantId -o tsv)
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
RG_ID=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)

# --- resolve the immutable owner/repo IDs from the GitHub API -------------
log "Resolving immutable GitHub IDs for ${GITHUB_ORG}/${GITHUB_REPO}"
GITHUB_API_AUTH=()
if [ -n "${GITHUB_TOKEN:-}" ]; then
  GITHUB_API_AUTH=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi
REPO_JSON=$(curl -fsS "${GITHUB_API_AUTH[@]}" \
  -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${GITHUB_ORG}/${GITHUB_REPO}") \
  || die "could not fetch https://api.github.com/repos/${GITHUB_ORG}/${GITHUB_REPO}" \
    " -- check GITHUB_ORG/GITHUB_REPO in config.env, or set GITHUB_TOKEN if the repo is" \
    " private or you are rate-limited"

GITHUB_OWNER_ID=$(printf '%s' "$REPO_JSON" | python3 -c \
  "import json, sys; print(json.load(sys.stdin)['owner']['id'])" 2>/dev/null) \
  || die "could not parse 'owner.id' from the GitHub API response for ${GITHUB_ORG}/${GITHUB_REPO}"
GITHUB_REPO_ID=$(printf '%s' "$REPO_JSON" | python3 -c \
  "import json, sys; print(json.load(sys.stdin)['id'])" 2>/dev/null) \
  || die "could not parse 'id' from the GitHub API response for ${GITHUB_ORG}/${GITHUB_REPO}"

# Belt and suspenders: refuse to build a subject from anything that isn't
# obviously a numeric GitHub ID, rather than silently trusting a malformed or
# unexpected API response.
[[ "$GITHUB_OWNER_ID" =~ ^[0-9]+$ ]] \
  || die "resolved owner id '${GITHUB_OWNER_ID}' is not numeric -- refusing to build the OIDC subject"
[[ "$GITHUB_REPO_ID" =~ ^[0-9]+$ ]] \
  || die "resolved repo id '${GITHUB_REPO_ID}' is not numeric -- refusing to build the OIDC subject"
log "  owner id: ${GITHUB_OWNER_ID}  repo id: ${GITHUB_REPO_ID}"

OIDC_ISSUER="https://token.actions.githubusercontent.com"
OIDC_AUDIENCE="api://AzureADTokenExchange"
OIDC_SUBJECT="repo:${GITHUB_ORG}@${GITHUB_OWNER_ID}/${GITHUB_REPO}@${GITHUB_REPO_ID}:environment:production"

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
# trigger alone. Truly idempotent: create if absent; if present but stale
# (e.g. built from a name-only subject by an older version of this script),
# update it rather than silently leaving a federated credential that will
# never match what GitHub actually sends.
log "Federated credential 'github-production': ${OIDC_SUBJECT}"
if ! resource_exists az identity federated-credential show \
  --name github-production --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP"; then
  az identity federated-credential create \
    --name github-production \
    --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
    --issuer "$OIDC_ISSUER" --subject "$OIDC_SUBJECT" --audiences "$OIDC_AUDIENCE" >/dev/null
  log "  created"
else
  CURRENT_SUBJECT=$(az identity federated-credential show \
    --name github-production --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" \
    --resource-group "$RESOURCE_GROUP" --query subject -o tsv)
  if [ "$CURRENT_SUBJECT" = "$OIDC_SUBJECT" ]; then
    log "  already up to date, skipping"
  else
    log "  stale subject found (${CURRENT_SUBJECT:-<empty>}) -- updating to the immutable-ID form"
    az identity federated-credential update \
      --name github-production \
      --identity-name "$GITHUB_DEPLOY_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
      --issuer "$OIDC_ISSUER" --subject "$OIDC_SUBJECT" --audiences "$OIDC_AUDIENCE" >/dev/null
    log "  updated"
  fi
fi

log "Done. Add these to the GitHub repo's 'production' Environment as VARIABLES (not secrets):"
log "  AZURE_CLIENT_ID       = ${DEPLOY_CLIENT_ID}"
log "  AZURE_TENANT_ID       = ${TENANT_ID}"
log "  AZURE_SUBSCRIPTION_ID = ${AZURE_SUBSCRIPTION_ID}"
log "None of these are secrets -- OIDC needs no client secret. See README.md."
