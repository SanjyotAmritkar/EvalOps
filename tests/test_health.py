"""Liveness (/health) and readiness (/ready) semantics + safe metadata.

Dependency checks are exercised directly (real SELECT 1 against the test DB, a
real Redis ping against a closed port); the endpoint's aggregation (200 vs 503)
is exercised by stubbing the two component checks so it needs no live Redis.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import evalops.api.health as health_mod

# --- /health -------------------------------------------------------------


def test_health_is_200_and_never_touches_a_dependency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If /health consulted either dependency check it would raise here.
    def _boom(*_a: object, **_k: object) -> dict[str, str]:
        raise AssertionError("/health must not consult a dependency")

    monkeypatch.setattr(health_mod, "_check_postgresql", _boom)
    monkeypatch.setattr(health_mod, "_check_redis", _boom)

    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "alive"
    assert set(body) >= {"status", "service", "version", "environment", "revision"}


def test_health_metadata_is_safe_and_missing_revision_is_null(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("EVALOPS_REVISION", "GIT_SHA", "GIT_COMMIT", "SOURCE_COMMIT"):
        monkeypatch.delenv(name, raising=False)

    body = client.get("/health").json()
    assert body["service"] == "evalops-api"
    assert body["revision"] is None  # explicit null, never fabricated
    # no secret-ish keys leaked into the metadata block
    assert not any(k in body for k in ("database_url", "broker_url", "config", "env"))

    monkeypatch.setenv("EVALOPS_REVISION", "abc1234")
    assert client.get("/health").json()["revision"] == "abc1234"


# --- component checks (real) ------------------------------------------


def test_check_postgresql_up_against_the_test_db(sessions: sessionmaker[Session]) -> None:
    assert health_mod._check_postgresql(sessions) == {"status": "up", "required": True}


def test_check_postgresql_down_when_the_factory_raises() -> None:
    def _broken() -> Session:
        raise RuntimeError("no db")

    result = health_mod._check_postgresql(_broken)  # type: ignore[arg-type]
    assert result["status"] == "down"
    assert result["required"] is True
    assert result["error_type"] == "RuntimeError"


def test_check_redis_down_against_a_closed_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_mod, "broker_url", lambda: "redis://127.0.0.1:1/0")
    result = health_mod._check_redis(required=True, timeout_s=0.2)
    assert result["status"] == "down"
    assert result["required"] is True


# --- /ready aggregation --------------------------------------------


def _stub(monkeypatch: pytest.MonkeyPatch, *, pg: dict[str, Any], redis: dict[str, Any]) -> None:
    monkeypatch.setattr(health_mod, "_check_postgresql", lambda _sessions: pg)
    monkeypatch.setattr(health_mod, "_check_redis", lambda required, timeout_s: redis)


def test_ready_is_200_when_every_required_component_is_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        pg={"status": "up", "required": True},
        redis={"status": "up", "required": True},
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["components"]["postgresql"]["status"] == "up"
    assert body["components"]["redis"]["status"] == "up"
    assert "version" in body and "environment" in body


def test_ready_is_503_when_postgresql_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        pg={"status": "down", "required": True, "error_type": "OperationalError"},
        redis={"status": "up", "required": True},
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


def test_ready_is_503_when_required_redis_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(
        monkeypatch,
        pg={"status": "up", "required": True},
        redis={"status": "down", "required": True, "error_type": "ConnectionError"},
    )
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["components"]["redis"]["status"] == "down"


def test_ready_stays_200_when_redis_is_optional_and_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVALOPS_REQUIRE_REDIS", "false")
    # real _check_redis with require_redis=False -> component reports required False
    monkeypatch.setattr(health_mod, "broker_url", lambda: "redis://127.0.0.1:1/0")
    monkeypatch.setattr(
        health_mod, "_check_postgresql", lambda _s: {"status": "up", "required": True}
    )
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["components"]["redis"]["status"] == "down"
    assert body["components"]["redis"]["required"] is False


def test_ready_does_not_require_an_llm_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # no OPENAI/ANTHROPIC/OLLAMA key set, both infra deps up -> ready
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _stub(
        monkeypatch,
        pg={"status": "up", "required": True},
        redis={"status": "up", "required": True},
    )
    assert client.get("/ready").status_code == 200
