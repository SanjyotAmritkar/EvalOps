"""The Celery experiment-execution task -- no broker, no HTTP.

Direct calls run the task body synchronously. The ``eager`` fixture exercises
Celery's dispatch path (``task_always_eager``) with no Redis.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import (
    EvaluationResultRepository,
    EvaluationRunRepository,
    RecordNotFound,
    unit_of_work,
)
from evalops.execution import ExecutionSpec
from evalops.worker.celery_app import celery_app
from evalops.worker.tasks import execute_experiment_task

_EVALUATORS: list[dict[str, Any]] = [{"type": "contains", "case_sensitive": False}]


@pytest.fixture
def eager() -> Iterator[None]:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False


def _patch_target(monkeypatch: pytest.MonkeyPatch, service: Any) -> None:
    monkeypatch.setattr("evalops.worker.tasks.execute_experiment_in_uow", service)
    monkeypatch.setattr("evalops.worker.tasks.get_session_factory", lambda: object())


def test_task_delegates_to_execution_service(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = Mock(return_value=Mock(model_dump=Mock(return_value={"decision": "pass"})))
    sentinel = object()
    monkeypatch.setattr("evalops.worker.tasks.execute_experiment_in_uow", spy)
    monkeypatch.setattr("evalops.worker.tasks.get_session_factory", lambda: sentinel)

    result = execute_experiment_task("exp-1", {"backend": "mock"}, _EVALUATORS)

    assert result == {"decision": "pass"}
    passed = spy.call_args.args
    assert passed[0] is sentinel  # the worker's own session factory, not a request session
    assert passed[1] == "exp-1"
    assert passed[2] == ExecutionSpec(backend="mock")
    assert passed[3] == _EVALUATORS


def test_task_reconstructs_execution_spec_from_json_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = Mock(return_value=Mock(model_dump=Mock(return_value={})))
    _patch_target(monkeypatch, spy)

    payload = json.loads(
        json.dumps({"backend": "ollama", "base_url": "http://x:11434", "timeout_seconds": 30})
    )
    execute_experiment_task("exp-1", payload, _EVALUATORS)

    spec = spy.call_args.args[2]
    assert spec == ExecutionSpec(backend="ollama", base_url="http://x:11434", timeout_seconds=30.0)
    assert isinstance(spec.timeout_seconds, float)  # int 30 in JSON -> float


def test_task_rejects_unknown_execution_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_target(monkeypatch, Mock())
    with pytest.raises(ValidationError):
        execute_experiment_task("exp-1", {"backend": "mock", "bogus": 1}, _EVALUATORS)


def test_task_propagates_service_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_target(monkeypatch, Mock(side_effect=RecordNotFound("no such experiment")))
    with pytest.raises(RecordNotFound):
        execute_experiment_task("missing", {"backend": "mock"}, _EVALUATORS)


def test_task_dispatches_eagerly_without_a_broker(
    eager: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = Mock(return_value=Mock(model_dump=Mock(return_value={"decision": "block"})))
    _patch_target(monkeypatch, spy)

    ok = execute_experiment_task.delay("exp-1", {"backend": "mock"}, _EVALUATORS)
    assert ok.get() == {"decision": "block"}

    _patch_target(monkeypatch, Mock(side_effect=RecordNotFound("gone")))
    with pytest.raises(RecordNotFound):
        execute_experiment_task.delay("exp-1", {"backend": "mock"}, _EVALUATORS).get()


def test_task_persists_through_service_without_http(
    runnable_experiment: str,
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("evalops.worker.tasks.get_session_factory", lambda: sessions)

    result = execute_experiment_task(runnable_experiment, {"backend": "mock"}, _EVALUATORS)

    assert result["decision"] == "pass"
    assert result["counts"] == {"cases": 1, "runs": 4, "failures": 0}

    with unit_of_work(sessions) as session:
        runs = EvaluationRunRepository(session).list_for_experiment(runnable_experiment)
        results = EvaluationResultRepository(session).list_for_experiment(runnable_experiment)
    assert len(runs) == 4
    assert [r.id for r in results] == [result["evaluation_result_id"]]
