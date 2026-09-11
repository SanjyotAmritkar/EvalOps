"""FastAPI application factory for the EvalOps read/write API.

Exposes the persistence layer plus liveness/readiness -- no evaluation
execution, dashboard, workers, or auth. Run locally with::

    uv run uvicorn evalops.api.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
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

_logger = get_logger("api")


def create_app(sessions: sessionmaker[Session] | None = None) -> FastAPI:
    """Build the API. ``sessions`` overrides the default engine (used by tests)."""
    configure_logging()

    app = FastAPI(title="EvalOps API", version=__version__)
    app.state.sessions = sessions or session_factory()

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

    app.include_router(health_router)
    for router in ROUTERS:
        app.include_router(router)

    return app


app = create_app()
