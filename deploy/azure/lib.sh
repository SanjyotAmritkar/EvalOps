#!/usr/bin/env bash
# Shared helpers for the deploy/azure/*.sh scripts (Phase 10, CP 10.5).
# Not run directly -- sourced by 00-provision-infra.sh / 01-provision-apps.sh /
# 02-deploy.sh.

set -euo pipefail

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*" >&2; }
die() {
  printf '\033[1;31m[deploy] error:\033[0m %s\n' "$*" >&2
  exit 1
}

# require_var NAME -- fail with a clear message if an expected variable is
# unset or empty. Never prints the value (some callers pass secrets).
require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    die "required variable \$$name is not set (see deploy/azure/config.env.example)"
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required on PATH but was not found"
}

# load_config [path] -- source deploy/azure/config.env (or the given path),
# which must exist (never the committed .example template).
load_config() {
  local path="${1:-$(dirname "${BASH_SOURCE[0]}")/config.env}"
  [ -f "$path" ] || die "$path not found -- copy config.env.example to config.env and fill it in"
  # shellcheck disable=SC1090
  source "$path"
}

# resource_exists <az show command...> -- true if the `az ... show` command
# succeeds (i.e. the resource already exists), for idempotent create-or-update.
resource_exists() {
  "$@" >/dev/null 2>&1
}
