"""Security configuration, read from the environment (Phase 10, CP 10.5).

Mirrors :class:`evalops.obs.settings.ObservabilitySettings`'s shape (a frozen
dataclass, ``from_env()`` reading fresh so tests can monkeypatch) but is kept
separate: observability settings are safe to echo back in a response body,
security settings never are.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ProductionConfigError(RuntimeError):
    """A required production setting is missing. Raised at app-startup time
    (``create_app``), before the process ever accepts a request -- a
    misconfigured production container should crash-loop loudly, not silently
    serve unauthenticated."""


def _split_origins(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    #: The single portfolio-scale API key. ``None`` means auth is not
    #: configured -- every request is allowed through (local development).
    #: Never logged, never echoed in any response.
    api_key: str | None
    #: Browser origins allowed to call the API cross-origin. Empty by default:
    #: the dashboard talks to the API through its own server-side proxy
    #: (never a browser cross-origin call), so this is defense-in-depth for a
    #: direct integration, not load-bearing for normal operation.
    cors_allow_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> SecuritySettings:
        raw_key = os.environ.get("EVALOPS_API_KEY")
        return cls(
            api_key=raw_key if raw_key and raw_key.strip() else None,
            cors_allow_origins=_split_origins(os.environ.get("EVALOPS_CORS_ALLOWED_ORIGINS")),
        )


def validate_production_config(*, environment: str, security: SecuritySettings) -> None:
    """Fail fast when a genuinely required production setting is missing.

    Called once from ``create_app`` -- never from a request path. Scope is
    deliberately narrow (CP 10.5): the one setting that would otherwise leave
    a production deployment silently unauthenticated.
    """
    if environment == "production" and security.api_key is None:
        raise ProductionConfigError(
            "EVALOPS_API_KEY must be set when EVALOPS_ENV=production "
            "(refusing to start an unauthenticated production API)"
        )
