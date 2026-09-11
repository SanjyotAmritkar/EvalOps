"""API-key authentication end to end (CP 10.5).

Unlike most tests in this suite, these build their own app instance (rather
than using the shared ``client`` fixture) because the API key must be present
in the environment *before* ``create_app()`` runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops.api.main import create_app
from evalops.security.settings import ProductionConfigError


def _client(sessions: sessionmaker[Session]) -> TestClient:
    return TestClient(create_app(sessions=sessions))


def test_no_key_configured_allows_unauthenticated_access(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EVALOPS_API_KEY", raising=False)
    with _client(sessions) as client:
        assert client.get("/projects").status_code == 200


def test_missing_header_is_401_when_a_key_is_configured(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    with _client(sessions) as client:
        resp = client.get("/projects")
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
        # the failure message never echoes the configured key
        assert "the-real-key" not in resp.text


def test_wrong_key_is_401(sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    with _client(sessions) as client:
        resp = client.get("/projects", headers={"Authorization": "Bearer wrong-guess"})
        assert resp.status_code == 401
        assert "the-real-key" not in resp.text
        assert "wrong-guess" not in resp.text


def test_malformed_scheme_is_401(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    with _client(sessions) as client:
        resp = client.get("/projects", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert resp.status_code == 401


def test_correct_key_is_authorized(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    with _client(sessions) as client:
        resp = client.get("/projects", headers={"Authorization": "Bearer the-real-key"})
        assert resp.status_code == 200


def test_correct_key_can_still_create_and_read_resources(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    auth = {"Authorization": "Bearer the-real-key"}
    with _client(sessions) as client:
        created = client.post("/projects", json={"name": "P"}, headers=auth)
        assert created.status_code == 201
        project_id = created.json()["id"]
        assert client.get(f"/projects/{project_id}", headers=auth).status_code == 200


def test_health_and_ready_do_not_require_the_key(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "the-real-key")
    with _client(sessions) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code in (200, 503)  # never 401


def test_production_without_a_key_refuses_to_start(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_ENV", "production")
    monkeypatch.delenv("EVALOPS_API_KEY", raising=False)
    with pytest.raises(ProductionConfigError):
        create_app(sessions=sessions)


def test_production_with_a_key_starts_and_enforces_it(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_ENV", "production")
    monkeypatch.setenv("EVALOPS_API_KEY", "prod-key")
    with _client(sessions) as client:
        assert client.get("/projects").status_code == 401
        assert (
            client.get("/projects", headers={"Authorization": "Bearer prod-key"}).status_code == 200
        )
        # interactive docs are a public-exposure surface with no purpose in
        # production
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
