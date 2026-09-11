"""Experiment + provider instrumentation: stable events, correlation fields,
and the privacy boundary (no prompt / output / dataset content / secrets)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import unit_of_work
from evalops.errors import ConfigError
from evalops.execution import ExecutionSpec
from evalops.execution_service import execute_experiment

_CONTAINS: list[dict[str, Any]] = [{"type": "contains", "case_sensitive": False}]


def _payloads(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [
        p
        for r in caplog.records
        if (p := getattr(r, "evalops_payload", None)) is not None and p.get("event") == event
    ]


def _all_payloads(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [p for r in caplog.records if (p := getattr(r, "evalops_payload", None)) is not None]


@pytest.fixture(autouse=True)
def _debug_events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="evalops")


def test_experiment_lifecycle_events_carry_correlation(
    sessions: sessionmaker[Session],
    runnable_experiment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with unit_of_work(sessions) as session:
        execute_experiment(session, runnable_experiment, ExecutionSpec(backend="mock"), _CONTAINS)

    (started,) = _payloads(caplog, "experiment_started")
    (decided,) = _payloads(caplog, "release_decision_computed")
    (completed,) = _payloads(caplog, "experiment_completed")

    for payload in (started, decided, completed):
        assert payload["experiment_id"] == runnable_experiment
        assert payload["project_id"]

    assert started["repeats"] == 2
    assert started["backend"] == "mock"
    assert decided["decision"] in {"pass", "block"}
    assert decided["gated"] is False  # runnable_experiment has no policy
    assert completed["run_count"] == 4
    assert completed["failure_count"] == 0
    assert isinstance(completed["duration_ms"], (int, float))
    assert completed["evaluation_result_id"]


def test_provider_call_events_have_context_but_no_prompt_or_output(
    sessions: sessionmaker[Session],
    runnable_experiment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with unit_of_work(sessions) as session:
        execute_experiment(session, runnable_experiment, ExecutionSpec(backend="mock"), _CONTAINS)

    calls = _payloads(caplog, "provider_call_completed")
    assert len(calls) == 4  # 2 versions x 1 case x 2 repeats
    for call in calls:
        assert call["provider"] == "openai"
        assert call["model"] == "m"
        assert call["outcome"] == "success"
        assert isinstance(call["duration_ms"], (int, float))
        # existing usage metadata only
        assert set(call) >= {"prompt_tokens", "completion_tokens", "cost_usd"}
        # never the content
        assert not any(k in call for k in ("prompt", "output", "text", "response", "input"))


def test_no_emitted_event_contains_prompt_output_or_dataset_content(
    sessions: sessionmaker[Session],
    runnable_experiment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with unit_of_work(sessions) as session:
        execute_experiment(session, runnable_experiment, ExecutionSpec(backend="mock"), _CONTAINS)

    import json

    blob = json.dumps(_all_payloads(caplog), default=str)
    # runnable_experiment: input "2+2?", rendered prompt "Q: 2+2?"
    assert "2+2?" not in blob
    assert "Q: 2+2?" not in blob
    assert '"prompt"' not in blob and '"output"' not in blob


def test_experiment_failed_event_on_a_bad_evaluator_config(
    sessions: sessionmaker[Session],
    runnable_experiment: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with unit_of_work(sessions) as session, pytest.raises(ConfigError):
        execute_experiment(
            session, runnable_experiment, ExecutionSpec(backend="mock"), [{"type": "regex_match"}]
        )

    (failed,) = _payloads(caplog, "experiment_failed")
    assert failed["experiment_id"] == runnable_experiment
    assert failed["error_type"] == "ConfigError"
    assert failed["error"].startswith("ConfigError:")
    assert not _payloads(caplog, "experiment_completed")


def test_provider_call_failed_event_when_the_candidate_provider_errors(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "2+2?", "expected_output": "4"}]},
    ).json()["id"]

    def _version(v: str, fail: bool) -> str:
        block: dict[str, Any] = {"responses": {"Q: 2+2?": "4"}, "default": "", "latency_ms": 1}
        if fail:
            block["fail_on"] = ["Q: 2+2?"]
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": v,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": "Q: ${input}",
                    "parameters": {"mock": block},
                },
            ).json()["id"]
        )

    experiment_id = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": _version("v1", False),
            "candidate_version_id": _version("v2", True),
            "repeats": 1,
        },
    ).json()["id"]

    caplog.clear()
    resp = client.post(
        f"/experiments/{experiment_id}/run",
        json={"execution": {"backend": "mock"}, "evaluators": _CONTAINS},
    )
    assert resp.status_code == 201

    failures = _payloads(caplog, "provider_call_failed")
    assert len(failures) == 1
    assert failures[0]["provider"] == "openai"
    assert failures[0]["outcome"] == "error"
    assert failures[0]["error_type"] == "ProviderError"
    assert "prompt" not in failures[0] and "output" not in failures[0]
    # the http request itself was still logged as completed (201, not 5xx)
    (http,) = _payloads(caplog, "http_request_completed")
    assert http["status"] == 201
    assert http["request_id"]
