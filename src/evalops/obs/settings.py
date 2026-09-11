"""Operational settings and build metadata, read from the environment.

No secrets, no full configuration -- only the safe metadata that health,
readiness and log lines expose. Values are read fresh from ``os.environ`` on
each :meth:`ObservabilitySettings.from_env` call so tests can monkeypatch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from evalops import __version__ as _package_version

#: Environment variables that may carry a git revision, in priority order. The
#: value is supplied by the deployment; EvalOps never shells out to git.
_REVISION_ENV = ("EVALOPS_REVISION", "GIT_SHA", "GIT_COMMIT", "SOURCE_COMMIT")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    service_name: str
    version: str
    environment: str
    revision: str | None
    log_level: str
    log_format: str  # "json" | "console"
    require_redis: bool
    readiness_timeout_s: float

    @classmethod
    def from_env(cls) -> ObservabilitySettings:
        revision = next((os.environ[name] for name in _REVISION_ENV if os.environ.get(name)), None)
        log_format = os.environ.get("EVALOPS_LOG_FORMAT", "json").strip().lower()
        if log_format not in ("json", "console"):
            log_format = "json"
        return cls(
            service_name=os.environ.get("EVALOPS_SERVICE_NAME", "evalops-api"),
            version=os.environ.get("EVALOPS_VERSION", _package_version),
            environment=os.environ.get("EVALOPS_ENV", "development"),
            revision=revision,
            log_level=os.environ.get("EVALOPS_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_format=log_format,
            require_redis=_bool_env("EVALOPS_REQUIRE_REDIS", default=True),
            readiness_timeout_s=_float_env("EVALOPS_READINESS_TIMEOUT_S", default=2.0),
        )

    def metadata(self) -> dict[str, str | None]:
        """The safe operational metadata block for health / readiness bodies."""
        return {
            "service": self.service_name,
            "version": self.version,
            "environment": self.environment,
            "revision": self.revision,
        }
