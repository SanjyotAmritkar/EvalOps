"""HTTP request-context middleware: X-Request-ID resolution + one completion event.

Uses a purpose-built app so a 5xx path is easy to exercise; the real API's
happy path is covered by ``test_health`` and ``test_obs_execution``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evalops.obs.context import get_field
from evalops.obs.middleware import RequestContextMiddleware


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestContextMiddleware)

    @application.get("/echo")
    def echo() -> dict[str, str | None]:
        return {"request_id": get_field("request_id")}

    @application.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @application.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("kaboom sk-should-not-leak")

    return application


@pytest.fixture
def events(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="evalops")
    return caplog


def _payloads(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [
        p
        for r in caplog.records
        if (p := getattr(r, "evalops_payload", None)) is not None and p.get("event") == event
    ]


def test_generates_a_request_id_and_echoes_it(
    app: FastAPI, events: pytest.LogCaptureFixture
) -> None:
    client = TestClient(app)
    resp = client.get("/echo")

    assert resp.status_code == 200
    rid = resp.headers["x-request-id"]
    assert len(rid) == 32  # uuid4 hex
    # the endpoint saw the same id through the contextvar
    assert resp.json()["request_id"] == rid

    (completed,) = _payloads(events, "http_request_completed")
    assert completed["request_id"] == rid
    assert completed["method"] == "GET"
    assert completed["route"] == "/echo"
    assert completed["status"] == 200
    assert isinstance(completed["duration_ms"], (int, float))


def test_accepts_a_well_formed_incoming_request_id(
    app: FastAPI, events: pytest.LogCaptureFixture
) -> None:
    client = TestClient(app)
    resp = client.get("/echo", headers={"X-Request-ID": "abc.DEF-123_456"})
    assert resp.headers["x-request-id"] == "abc.DEF-123_456"
    assert resp.json()["request_id"] == "abc.DEF-123_456"
    (completed,) = _payloads(events, "http_request_completed")
    assert completed["request_id"] == "abc.DEF-123_456"


@pytest.mark.parametrize(
    "bad",
    ["has space", "inject\nnewline", "x" * 200, "semi;colon", ""],
)
def test_rejects_unsafe_incoming_request_id_and_generates_one(app: FastAPI, bad: str) -> None:
    client = TestClient(app)
    resp = client.get("/echo", headers={"X-Request-ID": bad})
    generated = resp.headers["x-request-id"]
    assert generated != bad
    assert len(generated) == 32


def test_normalises_the_route_template_not_the_concrete_path(
    app: FastAPI, events: pytest.LogCaptureFixture
) -> None:
    TestClient(app).get("/items/42")
    (completed,) = _payloads(events, "http_request_completed")
    assert completed["route"] == "/items/{item_id}"


def test_logs_a_failure_event_without_leaking_the_message(
    app: FastAPI, events: pytest.LogCaptureFixture
) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500

    failed = _payloads(events, "http_request_failed")
    assert len(failed) == 1
    assert failed[0]["error_type"] == "RuntimeError"
    assert failed[0]["route"] == "/boom"
    assert failed[0]["request_id"]  # correlation still recorded on the failure
    # the failure event carries no free-form message field at all
    assert "error" not in failed[0]
    assert "message" not in failed[0]
    # nothing in any emitted event contains the secret-shaped token from the raise
    for record in events.records:
        payload = getattr(record, "evalops_payload", {}) or {}
        assert "sk-should-not-leak" not in json.dumps(payload, default=str)
