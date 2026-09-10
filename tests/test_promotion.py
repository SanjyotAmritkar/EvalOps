"""Promotion of production traces into a replayable regression Dataset (CP 8.2).

Covers the backend operation (``evalops.promotion.promote_traces_to_dataset``),
the ``POST /projects/{id}/trace-datasets`` endpoint, and a deterministic
end-to-end proof that a promoted dataset runs through the existing
experiment / evaluation / release-gate path with no trace-specific logic.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import (
    DatasetRepository,
    ProductionTraceRepository,
    RecordConflict,
    RecordNotFound,
    unit_of_work,
)
from evalops.domain.enums import CaseOrigin
from evalops.domain.errors import DomainValidationError
from evalops.errors import ConfigError
from evalops.execution import ExecutionSpec
from evalops.execution_service import execute_experiment_in_uow
from evalops.promotion import promote_traces_to_dataset


def _project(client: TestClient, name: str = "Support QA") -> str:
    return str(client.post("/projects", json={"name": name}).json()["id"])


def _system_version(client: TestClient, project_id: str, version: str, **params: Any) -> str:
    body: dict[str, Any] = {
        "name": "cfg",
        "version": version,
        "provider": "openai",
        "model": "m",
        "prompt_template": "Q: ${input}",
    }
    body.update(params)
    return str(client.post(f"/projects/{project_id}/system-versions", json=body).json()["id"])


def _trace(
    client: TestClient,
    project_id: str,
    system_version_id: str,
    *,
    input: str,
    reference_output: str | None = None,
    output: str = "",
) -> str:
    body: dict[str, Any] = {
        "system_version_id": system_version_id,
        "input": input,
        "output": output,
    }
    if reference_output is not None:
        body["reference_output"] = reference_output
    response = client.post(f"/projects/{project_id}/traces", json=body)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --- the backend operation -------------------------------------------


def test_promote_multiple_traces_maps_input_reference_and_provenance(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t1 = _trace(client, project_id, sv_id, input="2+2?", reference_output="4", output="four")
    t2 = _trace(client, project_id, sv_id, input="capital of France?", reference_output="Paris")

    with unit_of_work(sessions) as session:
        dataset = promote_traces_to_dataset(
            session, project_id=project_id, trace_ids=[t1, t2], name="prod-regression"
        )

    assert dataset.project_id == project_id
    assert dataset.name == "prod-regression"
    assert dataset.version == 1
    assert len(dataset.cases) == 2

    first, second = dataset.cases
    assert first.input == "2+2?"
    assert first.expected_output == "4"  # the reference, NOT trace.output ("four")
    assert first.origin is CaseOrigin.PROMOTED_TRACE
    assert first.source_trace_id == t1
    assert second.input == "capital of France?"
    assert second.expected_output == "Paris"
    assert second.source_trace_id == t2


def test_promotion_preserves_request_order(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    ids = [
        _trace(client, project_id, sv_id, input=f"q{i}", reference_output=f"a{i}") for i in range(5)
    ]
    requested = [ids[3], ids[0], ids[4], ids[1], ids[2]]

    with unit_of_work(sessions) as session:
        dataset = promote_traces_to_dataset(
            session, project_id=project_id, trace_ids=requested, name="ordered"
        )

    assert [c.source_trace_id for c in dataset.cases] == requested


def test_trace_without_reference_promotes_with_no_oracle(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    # a trace with an actual output but no recorded reference
    t = _trace(client, project_id, sv_id, input="freeform?", output="a model answer")

    with unit_of_work(sessions) as session:
        dataset = promote_traces_to_dataset(
            session, project_id=project_id, trace_ids=[t], name="no-ref"
        )

    assert dataset.cases[0].expected_output is None  # never fabricated from output
    assert dataset.cases[0].source_trace_id == t


def test_empty_selection_is_rejected(client: TestClient, sessions: sessionmaker[Session]) -> None:
    project_id = _project(client)
    with unit_of_work(sessions) as session, pytest.raises(ConfigError):
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[], name="x")


def test_duplicate_trace_ids_are_rejected(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t = _trace(client, project_id, sv_id, input="q", reference_output="a")
    with unit_of_work(sessions) as session, pytest.raises(ConfigError, match="duplicate"):
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[t, t], name="dupes")


def test_unknown_trace_is_rejected(client: TestClient, sessions: sessionmaker[Session]) -> None:
    project_id = _project(client)
    with unit_of_work(sessions) as session, pytest.raises(RecordNotFound):
        promote_traces_to_dataset(
            session, project_id=project_id, trace_ids=["no-such-trace"], name="x"
        )


def test_unknown_project_is_rejected(sessions: sessionmaker[Session]) -> None:
    with unit_of_work(sessions) as session, pytest.raises(RecordNotFound):
        promote_traces_to_dataset(session, project_id="nope", trace_ids=["whatever"], name="x")


def test_cross_project_trace_is_rejected(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_a = _project(client, "A")
    project_b = _project(client, "B")
    sv_b = _system_version(client, project_b, "v1")
    t_b = _trace(client, project_b, sv_b, input="q", reference_output="a")

    with unit_of_work(sessions) as session, pytest.raises(ConfigError, match="belongs to project"):
        promote_traces_to_dataset(session, project_id=project_a, trace_ids=[t_b], name="x")


def test_blank_name_is_a_domain_conflict(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t = _trace(client, project_id, sv_id, input="q", reference_output="a")
    with unit_of_work(sessions) as session, pytest.raises(DomainValidationError):
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[t], name="   ")


# --- atomicity & trace immutability --------------------------------


def test_promotion_is_atomic_on_a_name_conflict(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t1 = _trace(client, project_id, sv_id, input="q1", reference_output="a1")
    t2 = _trace(client, project_id, sv_id, input="q2", reference_output="a2")

    with unit_of_work(sessions) as session:
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[t1], name="taken")

    with pytest.raises(RecordConflict), unit_of_work(sessions) as session:
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[t1, t2], name="taken")

    # exactly one dataset for that name -- the failed promotion left nothing
    with unit_of_work(sessions) as session:
        named = [
            d for d in DatasetRepository(session).list_for_project(project_id) if d.name == "taken"
        ]
    assert len(named) == 1
    assert len(named[0].cases) == 1


def test_promotion_never_mutates_the_source_traces(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t1 = _trace(client, project_id, sv_id, input="q1", reference_output="a1", output="o1")
    t2 = _trace(client, project_id, sv_id, input="q2", output="o2")

    with unit_of_work(sessions) as session:
        before = {t.id: t for t in ProductionTraceRepository(session).list_for_project(project_id)}

    with unit_of_work(sessions) as session:
        promote_traces_to_dataset(session, project_id=project_id, trace_ids=[t1, t2], name="rs")

    with unit_of_work(sessions) as session:
        after = {t.id: t for t in ProductionTraceRepository(session).list_for_project(project_id)}

    assert after == before  # frozen dataclasses compare by value


# --- API -----------------------------------------------------------


def test_endpoint_returns_the_normal_dataset_representation(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t1 = _trace(client, project_id, sv_id, input="2+2?", reference_output="4")
    t2 = _trace(client, project_id, sv_id, input="3+3?", reference_output="6")

    response = client.post(
        f"/projects/{project_id}/trace-datasets",
        json={"name": "production-regression-set", "trace_ids": [t1, t2]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "production-regression-set"
    assert body["project_id"] == project_id
    assert [c["input"] for c in body["cases"]] == ["2+2?", "3+3?"]
    assert [c["expected_output"] for c in body["cases"]] == ["4", "6"]
    assert [c["source_trace_id"] for c in body["cases"]] == [t1, t2]
    assert all(c["origin"] == "promoted_trace" for c in body["cases"])

    # retrievable through the existing dataset API, unchanged
    fetched = client.get(f"/datasets/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert body["id"] in {d["id"] for d in client.get(f"/projects/{project_id}/datasets").json()}


def test_endpoint_empty_trace_ids_is_422(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/trace-datasets", json={"name": "x", "trace_ids": []}
    )
    assert response.status_code == 422


def test_endpoint_duplicate_ids_is_422(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t = _trace(client, project_id, sv_id, input="q", reference_output="a")
    response = client.post(
        f"/projects/{project_id}/trace-datasets", json={"name": "x", "trace_ids": [t, t]}
    )
    assert response.status_code == 422


def test_endpoint_unknown_trace_is_404(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/trace-datasets", json={"name": "x", "trace_ids": ["ghost"]}
    )
    assert response.status_code == 404


def test_endpoint_cross_project_trace_is_422(client: TestClient) -> None:
    project_a = _project(client, "A")
    project_b = _project(client, "B")
    sv_b = _system_version(client, project_b, "v1")
    t_b = _trace(client, project_b, sv_b, input="q", reference_output="a")

    response = client.post(
        f"/projects/{project_a}/trace-datasets", json={"name": "x", "trace_ids": [t_b]}
    )
    assert response.status_code == 422


def test_endpoint_duplicate_name_is_409(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id, "v1")
    t = _trace(client, project_id, sv_id, input="q", reference_output="a")
    payload = {"name": "same", "trace_ids": [t]}
    assert client.post(f"/projects/{project_id}/trace-datasets", json=payload).status_code == 201
    assert client.post(f"/projects/{project_id}/trace-datasets", json=payload).status_code == 409


# --- deterministic end-to-end replay ------------------------------


def test_promoted_dataset_runs_through_the_existing_evaluation_path(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    """A promoted dataset is an ordinary dataset: Dataset -> Experiment ->
    Eval Runner -> statistical evidence -> release gate, with mock execution
    and zero trace-specific handling."""
    project_id = _project(client)
    ingest_sv = _system_version(client, project_id, "ingest")
    t1 = _trace(client, project_id, ingest_sv, input="2+2?", reference_output="4")
    t2 = _trace(client, project_id, ingest_sv, input="3+3?", reference_output="6")

    dataset_id = client.post(
        f"/projects/{project_id}/trace-datasets",
        json={"name": "replay-set", "trace_ids": [t1, t2]},
    ).json()["id"]

    mock_params = {
        "parameters": {
            "mock": {
                "responses": {"Q: 2+2?": "4", "Q: 3+3?": "6"},
                "default": "",
                "latency_ms": 40,
            }
        }
    }
    baseline = _system_version(client, project_id, "v1", **mock_params)
    candidate = _system_version(client, project_id, "v2", **mock_params)
    experiment_id = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": baseline,
            "candidate_version_id": candidate,
            "repeats": 2,
        },
    ).json()["id"]

    result = execute_experiment_in_uow(
        sessions,
        experiment_id,
        ExecutionSpec(backend="mock"),
        [{"type": "contains", "case_sensitive": False}],
    )

    assert result.decision == "pass"
    assert result.counts == {"cases": 2, "runs": 8, "failures": 0}
    # the normal statistical view is produced -- nothing trace-aware
    assert any(m.metric == "success_rate" for m in result.metrics)
    assert {e.metric for e in result.evidence}  # paired-bootstrap evidence exists

    # provenance survived into the persisted, replayed dataset
    with unit_of_work(sessions) as session:
        stored = DatasetRepository(session).get(dataset_id)
    assert stored is not None
    assert {c.source_trace_id for c in stored.cases} == {t1, t2}
    assert all(c.origin is CaseOrigin.PROMOTED_TRACE for c in stored.cases)
