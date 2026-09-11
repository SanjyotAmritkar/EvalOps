"""Liveness, readiness, and safe operational metadata.

``GET /health`` -- is the process up? Cheap, no dependency touched, always 200.
Use it for a container/liveness probe.

``GET /ready`` -- can the process serve requests? Checks PostgreSQL connectivity
(a read-only ``SELECT 1``) and, when Redis is required, the Celery broker. Any
required dependency down => HTTP 503 with per-component status. An LLM provider
is never part of readiness. No writes, no destructive checks.

Both bodies carry the safe metadata block (service / version / environment /
revision) and never a secret or full configuration.
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from evalops.obs.settings import ObservabilitySettings
from evalops.worker.celery_app import broker_url

health = APIRouter(tags=["health"])


def _check_postgresql(sessions: sessionmaker[Session]) -> dict[str, Any]:
    try:
        session = sessions()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except Exception as exc:
        return {"status": "down", "required": True, "error_type": type(exc).__name__}
    return {"status": "up", "required": True}


def _check_redis(required: bool, timeout_s: float) -> dict[str, Any]:
    try:
        import redis  # celery[redis] dependency
    except Exception:  # pragma: no cover - redis always present via celery[redis]
        return {"status": "unknown", "required": required, "error_type": "redis-unavailable"}

    client = None
    try:
        client = redis.from_url(  # type: ignore[no-untyped-call]
            broker_url(), socket_connect_timeout=timeout_s, socket_timeout=timeout_s
        )
        client.ping()
    except Exception as exc:
        return {"status": "down", "required": required, "error_type": type(exc).__name__}
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()
    return {"status": "up", "required": required}


@health.get("/health")
def liveness() -> dict[str, Any]:
    """Process is alive. No dependency is consulted."""
    settings = ObservabilitySettings.from_env()
    return {"status": "alive", **settings.metadata()}


@health.get("/ready")
def readiness(request: Request, response: Response) -> dict[str, Any]:
    """Dependency readiness. 200 when every *required* component is up, else 503."""
    settings = ObservabilitySettings.from_env()
    sessions: sessionmaker[Session] = request.app.state.sessions

    components = {
        "postgresql": _check_postgresql(sessions),
        "redis": _check_redis(settings.require_redis, settings.readiness_timeout_s),
    }

    ready = all(
        component["status"] == "up"
        for component in components.values()
        if component.get("required")
    )
    response.status_code = 200 if ready else 503
    return {
        "status": "ready" if ready else "not_ready",
        **settings.metadata(),
        "components": components,
    }
