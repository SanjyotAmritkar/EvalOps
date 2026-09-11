"""EvalOps API security (Phase 10, CP 10.5).

A small, portfolio-appropriate layer: one flat API key
(:func:`~evalops.security.auth.require_api_key`), a handful of baseline
response headers (:class:`~evalops.security.headers.SecurityHeadersMiddleware`),
and deliberate CORS/startup-validation settings
(:mod:`evalops.security.settings`). No OAuth, no user accounts, no RBAC --
see ``docs/ARCHITECTURE.md`` for the explicit non-goals.
"""

from __future__ import annotations

from evalops.security.auth import require_api_key
from evalops.security.headers import SecurityHeadersMiddleware
from evalops.security.settings import (
    ProductionConfigError,
    SecuritySettings,
    validate_production_config,
)

__all__ = [
    "ProductionConfigError",
    "SecurityHeadersMiddleware",
    "SecuritySettings",
    "require_api_key",
    "validate_production_config",
]
