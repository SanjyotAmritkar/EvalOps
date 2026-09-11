"""Simple API-key authentication for the production API (Phase 10, CP 10.5).

One flat key, no roles, no sessions -- appropriate for a portfolio deployment,
not a substitute for a real identity platform (OAuth/RBAC is explicitly out of
scope; see docs/ARCHITECTURE.md). Callers send ``Authorization: Bearer <key>``;
the same header works from curl, the dashboard's server-side proxy, or any
other direct client.

``require_api_key`` is a FastAPI dependency attached per-router in
``api/main.py`` -- every router except ``health`` (liveness/readiness must
stay reachable by an unauthenticated platform probe). When
``EVALOPS_API_KEY`` is unset, it is a no-op: every request passes, so local
development and the existing test suite are unaffected. When it is set, a
missing or mismatched key is 401 -- there is only one key and no notion of
"authenticated but forbidden", so 403 is never returned here.
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from evalops.obs.logging import get_logger, log_event
from evalops.security.settings import SecuritySettings

_logger = get_logger("security")

# auto_error=False: a missing/malformed Authorization header must reach our
# own handler (a uniform 401 with no scheme details), not FastAPI's default.
_bearer_scheme = HTTPBearer(auto_error=False, description="EvalOps API key")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing or invalid API key.",
    headers={"WWW-Authenticate": "Bearer"},
)


def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> None:
    """Enforce ``Authorization: Bearer <EVALOPS_API_KEY>`` when a key is configured."""
    configured = SecuritySettings.from_env().api_key
    if configured is None:
        return  # auth not configured -- local/dev mode, pass through

    if credentials is None or credentials.scheme.lower() != "bearer":
        log_event(_logger, "api_auth_failed", level=logging.WARNING, reason="missing_credentials")
        raise _UNAUTHORIZED

    # Constant-time comparison: a key-guessing attacker must not be able to
    # learn anything from response-time differences.
    if not hmac.compare_digest(credentials.credentials, configured):
        log_event(_logger, "api_auth_failed", level=logging.WARNING, reason="key_mismatch")
        raise _UNAUTHORIZED
