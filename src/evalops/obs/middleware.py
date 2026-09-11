"""Pure-ASGI request correlation + HTTP observability.

Implemented as a bare ASGI middleware (not ``BaseHTTPMiddleware``) so the
correlation :mod:`contextvars` set here are visible to the endpoint and every
downstream call in the same task -- ``BaseHTTPMiddleware`` runs the app in a
child task where that would not hold.

Per request it: resolves a safe ``X-Request-ID`` (incoming if well-formed, else
a fresh hex id), binds it into the correlation context, echoes it on the
response, and logs exactly one ``http_request_completed`` (or
``http_request_failed``) event with method, normalised route, status and
duration. It never reads the body, headers beyond ``X-Request-ID``, cookies or
the query string.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from evalops.obs.context import bind, reset
from evalops.obs.logging import get_logger, log_event

_REQUEST_ID_HEADER = "x-request-id"
#: Accept only short, printable, unambiguous ids -- defeats header/log injection.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")

_logger = get_logger("http")


def _resolve_request_id(scope: Scope) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name == _REQUEST_ID_HEADER.encode():
            candidate = bytes(raw_value).decode("latin-1", "replace").strip()
            if _VALID_REQUEST_ID.match(candidate):
                return candidate
            break
    return uuid4().hex


def _route(scope: Scope) -> str:
    """The templated path (``/experiments/{experiment_id}/runs``) when routing
    matched, else the raw path. Never the query string."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    raw_path = scope.get("path", "")
    return str(raw_path) if raw_path else "/"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        method = scope.get("method", "GET")
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[_REQUEST_ID_HEADER] = request_id
            await send(message)

        token = bind(request_id=request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            log_event(
                _logger,
                "http_request_failed",
                level=logging.ERROR,
                method=method,
                route=_route(scope),
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            level = logging.ERROR if status_code >= 500 else logging.INFO
            log_event(
                _logger,
                "http_request_completed",
                level=level,
                method=method,
                route=_route(scope),
                status=status_code,
                duration_ms=duration_ms,
            )
        finally:
            reset(token)


__all__ = ["RequestContextMiddleware"]
