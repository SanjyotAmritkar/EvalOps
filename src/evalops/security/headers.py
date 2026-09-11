"""Baseline security response headers (Phase 10, CP 10.5).

A pure-ASGI middleware (not ``BaseHTTPMiddleware``, consistent with
``evalops.obs.middleware.RequestContextMiddleware``) that sets a small,
well-understood set of headers on every response. This is a JSON API, not an
HTML app, so there is deliberately no bespoke Content-Security-Policy here --
that would mostly matter for the interactive ``/docs``/``/redoc`` pages, which
are disabled outright in production (see ``api/main.py``).
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    # Only enforced by browsers over an actual HTTPS connection; harmless over
    # plain HTTP (local dev / container-internal traffic behind a TLS-
    # terminating ingress such as Azure Container Apps).
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


__all__ = ["SecurityHeadersMiddleware"]
