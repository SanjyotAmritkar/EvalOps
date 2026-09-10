"""API: production-trace ingestion / read (Phase 8, CP 8.1).

    POST /projects/{project_id}/traces
    GET  /projects/{project_id}/traces
    GET  /traces/{trace_id}

FastAPI TestClient over temp-file SQLite (see conftest). No network.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _project(client: TestClient, name: str = "Support QA") -> str:
    response = client.post("/projects", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def _system_version(client: TestClient, project_id: str, version: str = "v1") -> str:
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


def _trace_body(system_version_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "system_version_id": system_version_id,
        "input": "How do I reset my password?",
    }
    body.update(overrides)
    return body


# --- create --------------------------------------------------------------


def test_create_trace_returns_201_and_persisted_shape(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(
        f"/projects/{project_id}/traces",
        json=_trace_body(
            sv_id,
            output="Use the reset link on the login page.",
            reference_output="Click 'Forgot password'.",
            metadata={"conversation_id": "c-1"},
            latency_ms=812.0,
            cost_usd=0.0004,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] and body["created_at"]
    assert body["project_id"] == project_id
    assert body["system_version_id"] == sv_id
    assert body["input"] == "How do I reset my password?"
    assert body["output"] == "Use the reset link on the login page."
    assert body["reference_output"] == "Click 'Forgot password'."
    assert body["metadata"] == {"conversation_id": "c-1"}
    assert body["latency_ms"] == 812.0
    assert body["cost_usd"] == 0.0004
    assert body["error"] is None
    assert body["origin"] == "production"


def test_create_trace_with_only_required_fields(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(f"/projects/{project_id}/traces", json=_trace_body(sv_id))

    assert response.status_code == 201
    body = response.json()
    assert body["output"] == ""
    assert body["reference_output"] is None
    assert body["metadata"] == {}
    assert body["latency_ms"] is None
    assert body["cost_usd"] is None


def test_create_trace_can_record_an_error_interaction(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(
        f"/projects/{project_id}/traces",
        json=_trace_body(sv_id, output="", error="provider timeout after 30s"),
    )

    assert response.status_code == 201
    assert response.json()["error"] == "provider timeout after 30s"


# --- retrieve / list ---------------------------------------------------


def test_get_trace_returns_persisted_data(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)
    created = client.post(
        f"/projects/{project_id}/traces", json=_trace_body(sv_id, output="ok")
    ).json()

    got = client.get(f"/traces/{created['id']}")

    assert got.status_code == 200
    assert got.json() == created


def test_list_traces_returns_only_this_projects_traces(client: TestClient) -> None:
    project_a = _project(client, "A")
    project_b = _project(client, "B")
    sv_a = _system_version(client, project_a)
    sv_b = _system_version(client, project_b)

    a1 = client.post(f"/projects/{project_a}/traces", json=_trace_body(sv_a, input="a1")).json()[
        "id"
    ]
    a2 = client.post(f"/projects/{project_a}/traces", json=_trace_body(sv_a, input="a2")).json()[
        "id"
    ]
    client.post(f"/projects/{project_b}/traces", json=_trace_body(sv_b, input="b1"))

    listed = client.get(f"/projects/{project_a}/traces")

    assert listed.status_code == 200
    ids = [t["id"] for t in listed.json()]
    assert ids == [a1, a2]  # oldest first, no project B traces
    assert all(t["project_id"] == project_a for t in listed.json())


# --- validation / not-found ------------------------------------------


def test_create_trace_unknown_project_is_404(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post("/projects/does-not-exist/traces", json=_trace_body(sv_id))

    assert response.status_code == 404


def test_create_trace_unknown_system_version_is_404(client: TestClient) -> None:
    project_id = _project(client)

    response = client.post(f"/projects/{project_id}/traces", json=_trace_body("no-such-version"))

    assert response.status_code == 404
    assert "system version" in response.json()["detail"]


def test_create_trace_with_system_version_from_another_project_is_422(client: TestClient) -> None:
    project_a = _project(client, "A")
    project_b = _project(client, "B")
    sv_b = _system_version(client, project_b)

    response = client.post(f"/projects/{project_a}/traces", json=_trace_body(sv_b))

    assert response.status_code == 422
    assert "does not belong" in response.json()["detail"]
    # and nothing was persisted
    assert client.get(f"/projects/{project_a}/traces").json() == []


def test_create_trace_missing_input_is_422(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(f"/projects/{project_id}/traces", json={"system_version_id": sv_id})

    assert response.status_code == 422


def test_create_trace_blank_input_is_422_from_domain(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(f"/projects/{project_id}/traces", json=_trace_body(sv_id, input="   "))

    assert response.status_code == 422


def test_create_trace_negative_latency_is_422_from_domain(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(
        f"/projects/{project_id}/traces", json=_trace_body(sv_id, latency_ms=-1.0)
    )

    assert response.status_code == 422


def test_create_trace_rejects_unknown_fields(client: TestClient) -> None:
    project_id = _project(client)
    sv_id = _system_version(client, project_id)

    response = client.post(
        f"/projects/{project_id}/traces",
        json=_trace_body(sv_id, request_headers={"authorization": "Bearer x"}),
    )

    assert response.status_code == 422


def test_get_missing_trace_is_404(client: TestClient) -> None:
    assert client.get("/traces/nope").status_code == 404


def test_list_traces_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/projects/nope/traces").status_code == 404
