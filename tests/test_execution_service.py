"""The persisted execution service, exercised without HTTP.

Proves the CP 4.1 boundary: orchestration (load / run / persist / gate) lives in
``evalops.execution_service`` and can be driven directly by a non-HTTP caller
(a future worker), with explicit transaction ownership and preserved error
semantics.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import (
    EvaluationResultRepository,
    EvaluationRunRepository,
    RecordConflict,
    RecordNotFound,
    unit_of_work,
)
from evalops.errors import ConfigError
from evalops.execution import ExecutionSpec
from evalops.execution_service import execute_experiment, execute_experiment_in_uow

_SPEC = ExecutionSpec(backend="mock")
_EVALUATORS: list[dict[str, Any]] = [{"type": "contains", "case_sensitive": False}]
_TEMPLATE = "Q: ${input}"
_RENDERED = "Q: 2+2?"


def _setup_experiment(client: TestClient) -> str:
    """Create project / dataset / two system versions / experiment via the API;
    return the experiment id. The API and the service share one database."""
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "2+2?", "expected_output": "4"}]},
    ).json()["id"]

    def _version(version: str) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": _TEMPLATE,
                    "parameters": {
                        "mock": {"responses": {_RENDERED: "4"}, "default": "", "latency_ms": 40}
                    },
                },
            ).json()["id"]
        )

    return str(
        client.post(
            f"/projects/{project_id}/experiments",
            json={
                "dataset_id": dataset_id,
                "baseline_version_id": _version("v1"),
                "candidate_version_id": _version("v2"),
                "repeats": 2,
            },
        ).json()["id"]
    )


def test_execute_experiment_runs_without_http_and_persists(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    experiment_id = _setup_experiment(client)

    result = execute_experiment_in_uow(sessions, experiment_id, _SPEC, _EVALUATORS)

    assert result.decision == "pass"
    assert result.counts == {"cases": 1, "runs": 4, "failures": 0}

    # durable, and visible from an independent transaction
    with unit_of_work(sessions) as session:
        runs = EvaluationRunRepository(session).list_for_experiment(experiment_id)
        results = EvaluationResultRepository(session).list_for_experiment(experiment_id)
    assert len(runs) == 4
    assert [r.id for r in results] == [result.evaluation_result_id]


def test_execute_experiment_missing_experiment_raises_record_not_found(
    sessions: sessionmaker[Session],
) -> None:
    with pytest.raises(RecordNotFound):
        execute_experiment_in_uow(sessions, "does-not-exist", _SPEC, _EVALUATORS)


def test_execute_experiment_second_run_raises_conflict_and_keeps_one_result(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    experiment_id = _setup_experiment(client)
    execute_experiment_in_uow(sessions, experiment_id, _SPEC, _EVALUATORS)

    with pytest.raises(RecordConflict):
        execute_experiment_in_uow(sessions, experiment_id, _SPEC, _EVALUATORS)

    with unit_of_work(sessions) as session:
        assert len(EvaluationResultRepository(session).list_for_experiment(experiment_id)) == 1


def test_execute_experiment_bad_spec_leaves_no_partial_state(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    experiment_id = _setup_experiment(client)

    with pytest.raises(ConfigError):
        execute_experiment_in_uow(
            sessions,
            experiment_id,
            _SPEC,
            [{"type": "regex_match"}],  # missing 'pattern'
        )

    with unit_of_work(sessions) as session:
        assert EvaluationRunRepository(session).list_for_experiment(experiment_id) == []
        assert EvaluationResultRepository(session).list_for_experiment(experiment_id) == []


def test_execute_experiment_does_not_commit_the_callers_session(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    """The session-taking entry point never commits: durability is the caller's
    unit of work, so a caller rollback discards everything."""
    experiment_id = _setup_experiment(client)

    session = sessions()
    try:
        result = execute_experiment(session, experiment_id, _SPEC, _EVALUATORS)
        assert result.counts["runs"] == 4  # the run itself succeeded
        session.rollback()
    finally:
        session.close()

    with unit_of_work(sessions) as check:
        assert EvaluationRunRepository(check).list_for_experiment(experiment_id) == []
        assert EvaluationResultRepository(check).list_for_experiment(experiment_id) == []


def test_http_and_direct_execution_produce_equivalent_summaries(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    via_http = client.post(
        f"/experiments/{_setup_experiment(client)}/run",
        json={"execution": {"backend": "mock"}, "evaluators": _EVALUATORS},
    ).json()
    via_service = execute_experiment_in_uow(
        sessions, _setup_experiment(client), _SPEC, _EVALUATORS
    ).model_dump()

    assert via_http["decision"] == via_service["decision"]
    assert via_http["gated"] == via_service["gated"]
    assert via_http["counts"] == via_service["counts"]
    assert {m["metric"] for m in via_http["metrics"]} == {
        m["metric"] for m in via_service["metrics"]
    }
