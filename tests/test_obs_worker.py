"""Async-job lifecycle events + correlation propagation across the Celery
boundary. Job-state semantics are unchanged (covered by test_worker.py); this
only asserts the structured events and the ids they carry."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.db import AsyncJobRepository, unit_of_work
from evalops.domain.enums import JobStatus
from evalops.errors import ConfigError
from evalops.obs.context import correlation_scope
from evalops.worker.celery_app import celery_app
from evalops.worker.tasks import enqueue_experiment_run, execute_experiment_task

_EVALUATORS: list[dict[str, Any]] = [{"type": "contains", "case_sensitive": False}]
_MOCK: dict[str, Any] = {"backend": "mock"}


@pytest.fixture
def eager() -> Iterator[None]:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False


@pytest.fixture
def use_test_db(monkeypatch: pytest.MonkeyPatch, sessions: sessionmaker[Session]) -> None:
    monkeypatch.setattr("evalops.worker.tasks.get_session_factory", lambda: sessions)


@pytest.fixture(autouse=True)
def _events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="evalops")


def _payloads(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    return [
        p
        for r in caplog.records
        if (p := getattr(r, "evalops_payload", None)) is not None and p.get("event") == event
    ]


def test_success_lifecycle_events_carry_all_correlation_ids(
    eager: None,
    use_test_db: None,
    runnable_experiment: str,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with correlation_scope(request_id="req-abc123"):
        job = enqueue_experiment_run(runnable_experiment, _MOCK, _EVALUATORS)

    (queued,) = _payloads(caplog, "async_job_queued")
    (started,) = _payloads(caplog, "async_job_started")
    (completed,) = _payloads(caplog, "async_job_completed")

    assert queued["job_id"] == job.id
    assert queued["experiment_id"] == runnable_experiment
    assert queued["request_id"] == "req-abc123"

    for payload in (started, completed):
        assert payload["job_id"] == job.id
        assert payload["experiment_id"] == runnable_experiment
        assert payload["request_id"] == "req-abc123"  # propagated across the boundary
        assert payload["celery_task_id"]  # assigned on the worker side

    assert completed["evaluation_result_id"]
    assert isinstance(completed["duration_ms"], (int, float))

    # the experiment events nested inside the task inherit the same request_id
    (exp_completed,) = _payloads(caplog, "experiment_completed")
    assert exp_completed["request_id"] == "req-abc123"
    assert exp_completed["job_id"] == job.id


def test_failure_lifecycle_event_and_unchanged_terminal_state(
    use_test_db: None,
    runnable_experiment: str,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    job = domain.AsyncJob(experiment_id=runnable_experiment)
    with unit_of_work(sessions) as session:
        AsyncJobRepository(session).add(job)

    caplog.clear()
    with correlation_scope(request_id="req-fail"), pytest.raises(ConfigError):
        execute_experiment_task.apply(
            args=[job.id, _MOCK, [{"type": "regex_match"}], {"request_id": "req-fail"}],
            throw=True,
        )

    assert not _payloads(caplog, "async_job_completed")
    (started,) = _payloads(caplog, "async_job_started")
    (failed,) = _payloads(caplog, "async_job_failed")
    assert started["request_id"] == "req-fail"
    assert failed["job_id"] == job.id
    assert failed["experiment_id"] == runnable_experiment
    assert failed["request_id"] == "req-fail"
    assert failed["error_type"] == "ConfigError"
    assert failed["error"].startswith("ConfigError:")
    assert isinstance(failed["duration_ms"], (int, float))

    # job-state semantics unchanged: still marked FAILED, no result linked
    with unit_of_work(sessions) as session:
        row = AsyncJobRepository(session).get(job.id)
    assert row is not None and row.status is JobStatus.FAILED
    assert row.evaluation_result_id is None


def test_dispatch_failure_is_logged_without_leaking(
    use_test_db: None,
    runnable_experiment: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from evalops.worker.tasks import DispatchError, execute_experiment_task

    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("broker down at redis://user:sk-secret@host:6379")

    monkeypatch.setattr(execute_experiment_task, "delay", _boom)

    with pytest.raises(DispatchError):
        enqueue_experiment_run(runnable_experiment, _MOCK, _EVALUATORS)

    (failed,) = _payloads(caplog, "async_job_dispatch_failed")
    assert failed["error_type"] == "RuntimeError"
    assert "sk-secret" not in failed["error"]
