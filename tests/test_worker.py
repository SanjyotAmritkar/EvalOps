"""The durable async-job lifecycle driven by the Celery task.

``.apply(throw=True)`` runs the task locally with a request context (no broker);
the ``eager`` fixture covers ``enqueue_experiment_run`` -> dispatch.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.db import (
    AsyncJobRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    RecordNotFound,
    unit_of_work,
)
from evalops.domain.enums import JobStatus
from evalops.errors import ConfigError
from evalops.execution import ExecutionSpec
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
    """Point the worker's session factory at the test database."""
    monkeypatch.setattr("evalops.worker.tasks.get_session_factory", lambda: sessions)


def _new_queued_job(sessions: sessionmaker[Session], experiment_id: str) -> str:
    job = domain.AsyncJob(experiment_id=experiment_id)
    with unit_of_work(sessions) as session:
        AsyncJobRepository(session).add(job)
    return job.id


def _load(sessions: sessionmaker[Session], job_id: str) -> domain.AsyncJob:
    with unit_of_work(sessions) as session:
        job = AsyncJobRepository(session).get(job_id)
    assert job is not None
    return job


def test_enqueue_runs_job_to_completion_and_links_result(
    eager: None,
    use_test_db: None,
    runnable_experiment: str,
    sessions: sessionmaker[Session],
) -> None:
    queued = enqueue_experiment_run(runnable_experiment, _MOCK, _EVALUATORS)
    assert queued.status is JobStatus.QUEUED

    job = _load(sessions, queued.id)
    assert job.status is JobStatus.COMPLETED
    assert job.error is None
    assert job.evaluation_result_id is not None
    assert job.celery_task_id is not None
    assert job.started_at is not None and job.completed_at is not None
    assert job.created_at <= job.started_at <= job.completed_at

    with unit_of_work(sessions) as session:
        results = EvaluationResultRepository(session).list_for_experiment(runnable_experiment)
        runs = EvaluationRunRepository(session).list_for_experiment(runnable_experiment)
    assert [r.id for r in results] == [job.evaluation_result_id]
    assert len(runs) == 4


def test_task_marks_job_failed_and_persists_no_evaluation_data(
    use_test_db: None,
    runnable_experiment: str,
    sessions: sessionmaker[Session],
) -> None:
    job_id = _new_queued_job(sessions, runnable_experiment)

    with pytest.raises(ConfigError):
        execute_experiment_task.apply(
            args=[job_id, _MOCK, [{"type": "regex_match"}]],  # missing 'pattern'
            throw=True,
        )

    job = _load(sessions, job_id)
    assert job.status is JobStatus.FAILED
    assert job.started_at is not None  # it reached running
    assert job.completed_at is not None
    assert job.error is not None and "ConfigError" in job.error
    assert job.evaluation_result_id is None

    # the evaluation transaction rolled back -- nothing partial persisted
    with unit_of_work(sessions) as session:
        assert EvaluationRunRepository(session).list_for_experiment(runnable_experiment) == []
        assert EvaluationResultRepository(session).list_for_experiment(runnable_experiment) == []


def test_unknown_job_id_raises_record_not_found(
    use_test_db: None, sessions: sessionmaker[Session]
) -> None:
    with pytest.raises(RecordNotFound):
        execute_experiment_task.apply(args=["no-such-job", _MOCK, _EVALUATORS], throw=True)


def test_task_delegates_to_the_execution_service(
    use_test_db: None,
    runnable_experiment: str,
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a real result row for the completed-job FK; the service call is stubbed
    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(
            domain.EvaluationResult(id="res-xyz", experiment_id=runnable_experiment, metrics=())
        )
    spy = Mock(
        return_value=Mock(
            evaluation_result_id="res-xyz",
            model_dump=Mock(return_value={"decision": "pass"}),
        )
    )
    monkeypatch.setattr("evalops.worker.tasks.execute_experiment_in_uow", spy)

    job_id = _new_queued_job(sessions, runnable_experiment)
    execute_experiment_task.apply(
        args=[job_id, {"backend": "ollama", "timeout_seconds": 30}, _EVALUATORS],
        throw=True,
    )

    factory, experiment_id, spec, evaluators = spy.call_args.args
    assert factory is sessions
    assert experiment_id == runnable_experiment
    assert spec == ExecutionSpec(backend="ollama", timeout_seconds=30.0)
    assert evaluators == _EVALUATORS

    job = _load(sessions, job_id)
    assert job.status is JobStatus.COMPLETED
    assert job.evaluation_result_id == "res-xyz"
