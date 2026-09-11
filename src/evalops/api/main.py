"""FastAPI application factory for the EvalOps read/write API.

Exposes the persistence layer plus liveness/readiness/auth -- no evaluation
execution, dashboard, or workers. Run locally with::

    uv run uvicorn evalops.api.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from evalops import __version__
from evalops.api.health import health as health_router
from evalops.api.routes import ROUTERS
from evalops.db import RecordConflict, RecordNotFound, session_factory
from evalops.domain.errors import DomainValidationError
from evalops.errors import ConfigError, JudgeError
from evalops.obs.logging import configure_logging, get_logger, log_event
from evalops.obs.middleware import RequestContextMiddleware
from evalops.obs.redact import safe_error
from evalops.obs.settings import ObservabilitySettings
from evalops.security import (
    SecurityHeadersMiddleware,
    SecuritySettings,
    require_api_key,
    validate_production_config,
)

_logger = get_logger("api")


def create_app(sessions: sessionmaker[Session] | None = None) -> FastAPI:
    """Build the API. ``sessions`` overrides the default engine (used by tests)."""
    configure_logging()

    observability = ObservabilitySettings.from_env()
    security = SecuritySettings.from_env()
    # Fail fast: a production container with no API key configured must not
    # start and silently serve unauthenticated. Never touches a request path.
    validate_production_config(environment=observability.environment, security=security)

    # Interactive docs/schema are a public-internet exposure surface with no
    # functional purpose in production; disabled there, kept in development.
    is_production = observability.environment == "production"
    app = FastAPI(
        title="EvalOps API",
        version=__version__,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.sessions = sessions or session_factory()

    # Middleware order matters (Starlette wraps in the *reverse* of add order,
    # so the last call here ends up outermost): CORS and security headers wrap
    # the request-context middleware, which stays truly outermost so it can
    # log every response -- including a CORS-rejected or 401 one -- exactly as
    # it always has.
    if security.cors_allow_origins:
        # Deliberately no wildcard-with-credentials: an explicit origin list,
        # and credentials (cookies) are never used by this API's auth scheme.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(security.cors_allow_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    app.add_middleware(SecurityHeadersMiddleware)
    # Outermost middleware: resolve X-Request-ID, bind the correlation context,
    # log one http_request_completed per request.
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RecordNotFound)
    async def _on_not_found(_: Request, exc: RecordNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RecordConflict)
    async def _on_conflict(_: Request, exc: RecordConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DomainValidationError)
    async def _on_domain_invalid(_: Request, exc: DomainValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ConfigError)
    async def _on_config_error(_: Request, exc: ConfigError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(JudgeError)
    async def _on_judge_error(_: Request, exc: JudgeError) -> JSONResponse:
        # The judge model itself returned something unusable -- an upstream
        # problem, not a bad request. Never a silent pass.
        log_event(_logger, "judge_error", level=logging.WARNING, error=safe_error(exc))
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    # Health/readiness stay reachable by an unauthenticated platform probe.
    app.include_router(health_router)
    # Every other route requires the API key (a no-op check when none is
    # configured -- see require_api_key).
    for router in ROUTERS:
        app.include_router(router, dependencies=[Depends(require_api_key)])

    return app


app = create_app()
