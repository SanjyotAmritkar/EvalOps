"""API tests -- FastAPI TestClient over a temp-file SQLite database (no Postgres)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from evalops.api.main import create_app
from evalops.db import Base, create_db_engine, session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.sqlite'}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: object, _: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    with TestClient(create_app(sessions=session_factory(engine))) as test_client:
        yield test_client


def _project(client: TestClient, name: str = "Support QA") -> str:
    response = client.post("/projects", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def _system_version(client: TestClient, project_id: str, version: str) -> str:
    response = client.post(
        f"/projects/{project_id}/system-versions",
        json={
            "name": "cfg",
            "version": version,
            "provider": "ollama",
            "model": "llama3.2",
            "prompt_template": "Q: ${input}",
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def _dataset(client: TestClient, project_id: str, name: str = "support") -> str:
    response = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": name,
            "version": 1,
            "cases": [{"input": "2+2?", "expected_output": "4"}],
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


# --- projects -------------------------------------------------------------


def test_create_get_and_list_project(client: TestClient) -> None:
    created = client.post("/projects", json={"name": "P1"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "P1" and body["id"] and body["created_at"]

    got = client.get(f"/projects/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body

    listed = client.get("/projects")
    assert listed.status_code == 200
    assert body["id"] in {p["id"] for p in listed.json()}


def test_get_missing_project_is_404(client: TestClient) -> None:
    assert client.get("/projects/nope").status_code == 404


def test_create_project_without_name_is_422(client: TestClient) -> None:
    assert client.post("/projects", json={}).status_code == 422


def test_create_project_blank_name_is_422_from_domain(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "   "})
    assert response.status_code == 422
    assert "non-empty" in response.json()["detail"]


def test_unknown_field_is_rejected(client: TestClient) -> None:
    assert client.post("/projects", json={"name": "P", "bogus": 1}).status_code == 422


# --- datasets -----------------------------------------------------------


def test_create_and_read_dataset_preserves_case_order(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "support",
            "version": 1,
            "cases": [
                {"input": "a", "expected_output": "1"},
                {"input": "b"},
                {"input": "c", "origin": "promoted_trace", "source_trace_id": "t-9"},
            ],
        },
    )
    assert response.status_code == 201
    dataset_id = response.json()["id"]

    got = client.get(f"/datasets/{dataset_id}").json()
    assert [c["input"] for c in got["cases"]] == ["a", "b", "c"]
    assert got["cases"][1]["expected_output"] is None
    assert got["cases"][2]["origin"] == "promoted_trace"
    assert got["cases"][2]["source_trace_id"] == "t-9"

    listed = client.get(f"/projects/{project_id}/datasets").json()
    assert [d["id"] for d in listed] == [dataset_id]


def test_create_dataset_under_missing_project_is_404(client: TestClient) -> None:
    response = client.post(
        "/projects/missing/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "x"}]},
    )
    assert response.status_code == 404


def test_create_dataset_with_no_cases_is_422_from_domain(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/datasets", json={"name": "d", "version": 1, "cases": []}
    )
    assert response.status_code == 422


def test_duplicate_dataset_name_and_version_is_409(client: TestClient) -> None:
    project_id = _project(client)
    _dataset(client, project_id, "support")
    conflict = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "support", "version": 1, "cases": [{"input": "y"}]},
    )
    assert conflict.status_code == 409


def test_list_datasets_for_missing_project_is_404(client: TestClient) -> None:
    assert client.get("/projects/nope/datasets").status_code == 404


# --- system versions ------------------------------------------------


def test_create_and_read_system_version(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/system-versions",
        json={
            "name": "cfg",
            "version": "v1",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "prompt_template": "Q: ${input}",
            "parameters": {"temperature": 0.0},
        },
    )
    assert response.status_code == 201
    version_id = response.json()["id"]

    got = client.get(f"/system-versions/{version_id}").json()
    assert got["provider"] == "openai"
    assert got["parameters"] == {"temperature": 0.0}
    assert got["rag_config"] is None

    listed = client.get(f"/projects/{project_id}/system-versions").json()
    assert [v["id"] for v in listed] == [version_id]


def test_create_system_version_bad_provider_is_422(client: TestClient) -> None:
    project_id = _project(client)
    response = client.post(
        f"/projects/{project_id}/system-versions",
        json={
            "name": "cfg",
            "version": "v1",
            "provider": "gpt-9",
            "model": "m",
            "prompt_template": "Q: ${input}",
        },
    )
    assert response.status_code == 422


def test_create_system_version_missing_project_is_404(client: TestClient) -> None:
    response = client.post(
        "/projects/nope/system-versions",
        json={
            "name": "cfg",
            "version": "v1",
            "provider": "ollama",
            "model": "m",
            "prompt_template": "Q: ${input}",
        },
    )
    assert response.status_code == 404


# --- release policies ---------------------------------------------


def test_create_get_and_list_release_policy(client: TestClient) -> None:
    created = client.post(
        "/release-policies",
        json={"name": "default", "thresholds": {"latency_ms.p95": 0.2}, "max_safety_violations": 0},
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    assert client.get(f"/release-policies/{policy_id}").json()["thresholds"] == {
        "latency_ms.p95": 0.2
    }
    assert policy_id in {p["id"] for p in client.get("/release-policies").json()}


def test_get_missing_release_policy_is_404(client: TestClient) -> None:
    assert client.get("/release-policies/nope").status_code == 404


# --- experiments -------------------------------------------------


def test_create_and_read_experiment(client: TestClient) -> None:
    project_id = _project(client)
    dataset_id = _dataset(client, project_id)
    baseline_id = _system_version(client, project_id, "v1")
    candidate_id = _system_version(client, project_id, "v2")

    response = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": baseline_id,
            "candidate_version_id": candidate_id,
            "repeats": 3,
        },
    )
    assert response.status_code == 201
    experiment_id = response.json()["id"]

    got = client.get(f"/experiments/{experiment_id}").json()
    assert got["repeats"] == 3
    assert got["release_policy_id"] is None

    listed = client.get(f"/projects/{project_id}/experiments").json()
    assert [e["id"] for e in listed] == [experiment_id]


def test_create_experiment_missing_dataset_is_404(client: TestClient) -> None:
    project_id = _project(client)
    baseline_id = _system_version(client, project_id, "v1")
    candidate_id = _system_version(client, project_id, "v2")
    response = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": "missing",
            "baseline_version_id": baseline_id,
            "candidate_version_id": candidate_id,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "dataset not found"


def test_create_experiment_same_baseline_and_candidate_is_422(client: TestClient) -> None:
    project_id = _project(client)
    dataset_id = _dataset(client, project_id)
    version_id = _system_version(client, project_id, "v1")
    response = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": version_id,
            "candidate_version_id": version_id,
        },
    )
    assert response.status_code == 422


def test_create_experiment_missing_project_is_404(client: TestClient) -> None:
    response = client.post(
        "/projects/nope/experiments",
        json={
            "dataset_id": "d",
            "baseline_version_id": "b",
            "candidate_version_id": "c",
        },
    )
    assert response.status_code == 404


# --- app sanity --------------------------------------------------


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/projects" in response.json()["paths"]
