"""Baseline security response headers and deliberate CORS configuration (CP 10.5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops.api.main import create_app


def test_security_headers_are_present_on_every_response(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"
    assert "strict-transport-security" in resp.headers


def test_security_headers_are_present_on_a_404_too(client: TestClient) -> None:
    resp = client.get("/projects/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_no_cors_header_when_no_origin_is_configured(client: TestClient) -> None:
    resp = client.get("/health", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in resp.headers


def test_configured_origin_gets_cors_headers_without_credentials(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_CORS_ALLOWED_ORIGINS", "https://dashboard.example.com")
    with TestClient(create_app(sessions=sessions)) as client:
        resp = client.get("/health", headers={"Origin": "https://dashboard.example.com"})
        assert resp.headers["access-control-allow-origin"] == "https://dashboard.example.com"
        # never wildcard-with-credentials: no cookie-based auth is offered
        assert "access-control-allow-credentials" not in resp.headers


def test_unconfigured_origin_gets_no_cors_headers(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_CORS_ALLOWED_ORIGINS", "https://dashboard.example.com")
    with TestClient(create_app(sessions=sessions)) as client:
        resp = client.get("/health", headers={"Origin": "https://evil.example.com"})
        assert "access-control-allow-origin" not in resp.headers
