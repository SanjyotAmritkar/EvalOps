"""FastAPI application factory for the EvalOps read/write API.

Exposes the persistence layer only -- no evaluation execution, dashboard,
workers, or auth. Run locally with::

    uv run uvicorn evalops.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from evalops.api.routes import ROUTERS
from evalops.db import RecordConflict, RecordNotFound, session_factory
from evalops.domain.errors import DomainValidationError
from evalops.errors import ConfigError


def create_app(sessions: sessionmaker[Session] | None = None) -> FastAPI:
    """Build the API. ``sessions`` overrides the default engine (used by tests)."""
    app = FastAPI(title="EvalOps API", version="0.1")
    app.state.sessions = sessions or session_factory()

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

    for router in ROUTERS:
        app.include_router(router)

    return app


app = create_app()
