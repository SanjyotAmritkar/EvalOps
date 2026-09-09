"""The asynchronous run API: POST /experiments/{id}/run-async and GET /jobs/{id}.

Celery dispatch is stubbed so the job stays queued; job lifecycle shapes are
built directly through the repository. No broker, no eager Celery.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.db import (
    AsyncJobRepository,
    EvaluationResultRepository,
    unit_of_work,
)
from evalops.worker.tasks import execute_experiment_task

_RUN_BODY: dict[str, Any] = {
    "execution": {"backend": "mock"},
    "evaluators": [{"type": "contains", "case_sensitive": False}],
}


@pytest.fixture
def dispatched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Stub Celery dispatch; return the list of positional args it was called with."""
    calls: list[tuple[Any, ...]] = []

    def _record(*args: Any, **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(execute_experiment_task, "delay", _record)
    return calls


def _make_job(sessions: sessionmaker[Session], experiment_id: str, target: str) -> str:
    job = domain.AsyncJob(experiment_id=experiment_id)
    with unit_of_work(sessions) as session:
        jobs = AsyncJobRepository(session)
        jobs.add(job)
        if target in ("running", "completed"):
            jobs.mark_running(job.id, celery_task_id="task-abc")
        if target == "completed":
            result = domain.EvaluationResult(experiment_id=experiment_id, metrics=())
            EvaluationResultRepository(session).add(result)
            jobs.mark_completed(job.id, result.id)
        if target == "failed":
            jobs.mark_failed(job.id, "x" * 5000)
    return job.id


# --- POST /experiments/{id}/run-async ---------------------------------------


def test_run_async_returns_202_queued_job_and_dispatches(
    client: TestClient,
    runnable_experiment: str,
    dispatched: list[tuple[Any, ...]],
) -> None:
    resp = client.post(f"/experiments/{runnable_experiment}/run-async", json=_RUN_BODY)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["experiment_id"] == runnable_experiment
    assert body["id"]
    assert (body["started_at"], body["completed_at"]) == (None, None)
    assert (body["evaluation_result_id"], body["error"], body["celery_task_id"]) == (
        None,
        None,
        None,
    )

    assert len(dispatched) == 1
    job_id, execution, evaluators = dispatched[0]
    assert job_id == body["id"]
    assert execution["backend"] == "mock" and "timeout_seconds" in execution
    assert evaluators == [{"type": "contains", "case_sensitive": False}]

    assert client.get(f"/jobs/{body['id']}").json() == body


def test_run_async_unknown_experiment_is_404(
    client: TestClient, dispatched: list[tuple[Any, ...]]
) -> None:
    assert client.post("/experiments/nope/run-async", json=_RUN_BODY).status_code == 404
    assert dispatched == []


def test_run_async_invalid_config_is_422(
    client: TestClient,
    runnable_experiment: str,
    dispatched: list[tuple[Any, ...]],
) -> None:
    base = f"/experiments/{runnable_experiment}/run-async"
    assert client.post(base, json={"evaluators": []}).status_code == 422
    assert (
        client.post(base, json={"evaluators": [{"type": "contains"}], "unexpected": 1}).status_code
        == 422
    )
    assert (
        client.post(
            base,
            json={"execution": {"backend": "bogus"}, "evaluators": [{"type": "contains"}]},
        ).status_code
        == 422
    )
    assert dispatched == []


def test_dispatch_failure_returns_500_and_marks_job_failed(
    client: TestClient,
    runnable_experiment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise ConnectionRefusedError("broker unreachable")

    monkeypatch.setattr(execute_experiment_task, "delay", _boom)

    resp = client.post(f"/experiments/{runnable_experiment}/run-async", json=_RUN_BODY)

    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "could not be dispatched" in detail
    match = re.search(r"job '([0-9a-f]{32})'", detail)
    assert match is not None

    job = client.get(f"/jobs/{match.group(1)}").json()
    assert job["status"] == "failed"
    assert "dispatch to the task broker failed" in job["error"]
    assert len(job["error"]) <= 2000

    # nothing evaluated
    assert client.get(f"/experiments/{runnable_experiment}/runs").json() == []


# --- GET /jobs/{job_id} ---------------------------------------------------


@pytest.mark.parametrize("target", ["queued", "running", "completed", "failed"])
def test_get_job_lifecycle_shapes(
    client: TestClient,
    sessions: sessionmaker[Session],
    runnable_experiment: str,
    target: str,
) -> None:
    job_id = _make_job(sessions, runnable_experiment, target)

    got = client.get(f"/jobs/{job_id}").json()
    assert got["status"] == target
    assert got["id"] == job_id and got["experiment_id"] == runnable_experiment

    if target == "queued":
        assert (
            got["started_at"],
            got["completed_at"],
            got["evaluation_result_id"],
            got["error"],
        ) == (None, None, None, None)
    elif target == "running":
        assert got["started_at"] is not None
        assert got["completed_at"] is None
        assert got["evaluation_result_id"] is None and got["error"] is None
        assert got["celery_task_id"] == "task-abc"
    elif target == "completed":
        assert got["started_at"] is not None and got["completed_at"] is not None
        assert got["evaluation_result_id"] is not None
        assert got["error"] is None
    else:  # failed
        assert got["completed_at"] is not None
        assert got["evaluation_result_id"] is None
        assert got["error"] is not None and len(got["error"]) <= 2000


def test_get_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/jobs/nope").status_code == 404


# --- backward compatibility -------------------------------------------


def test_sync_run_endpoint_is_unchanged(client: TestClient, runnable_experiment: str) -> None:
    resp = client.post(f"/experiments/{runnable_experiment}/run", json=_RUN_BODY)

    assert resp.status_code == 201
    body = resp.json()
    assert set(body) >= {
        "decision",
        "gated",
        "reasons",
        "counts",
        "metrics",
        "evaluation_result_id",
    }
    assert body["counts"]["runs"] == 4
    assert "status" not in body  # the sync response is a RunResponse, not a job
