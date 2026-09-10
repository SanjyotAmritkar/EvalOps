"""API: agent tool-call evidence + labels round-trip through the existing
dataset / run / results endpoints (Phase 9, CP 9.2). MockProvider only.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_TEMPLATE = "Q: ${input}"


def _mock_params(*, wrong_args: bool) -> dict[str, Any]:
    return {
        "mock": {
            "responses": {"Q: find cats": "ok"},
            "tool_calls": {
                "Q: find cats": [
                    {"name": "search", "arguments": {"q": "dogs" if wrong_args else "cats"}},
                    {"name": "summarize", "arguments": {}},
                ]
            },
            "latency_ms": 5,
        }
    }


def test_dataset_expected_tool_calls_round_trip(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    created = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "agent",
            "version": 1,
            "cases": [
                {
                    "input": "find cats",
                    "expected_tool_calls": [
                        {"name": "search", "arguments": {"q": "cats"}},
                        {"name": "summarize"},
                    ],
                },
                {"input": "plain", "expected_output": "x"},
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["cases"][0]["expected_tool_calls"] == [
        {"name": "search", "arguments": {"q": "cats"}},
        {"name": "summarize", "arguments": None},
    ]
    assert body["cases"][1]["expected_tool_calls"] == []
    assert client.get(f"/datasets/{body['id']}").json() == body


def test_run_exposes_tool_evidence_and_agent_metrics(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "agent",
            "version": 1,
            "cases": [
                {
                    "input": "find cats",
                    "expected_tool_calls": [
                        {"name": "search", "arguments": {"q": "cats"}},
                        {"name": "summarize"},
                    ],
                }
            ],
        },
    ).json()["id"]

    def _version(version: str, *, wrong: bool) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": _TEMPLATE,
                    "parameters": _mock_params(wrong_args=wrong),
                },
            ).json()["id"]
        )

    experiment_id = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": _version("v1", wrong=False),
            "candidate_version_id": _version("v2", wrong=True),
            "repeats": 2,
        },
    ).json()["id"]

    run = client.post(
        f"/experiments/{experiment_id}/run",
        json={
            "execution": {"backend": "mock"},
            "evaluators": [
                {"type": "tool_selection", "min_score": 1.0},
                {"type": "tool_arguments", "min_score": 1.0},
            ],
        },
    )
    assert run.status_code == 201
    payload = run.json()
    metrics = {m["metric"]: m for m in payload["metrics"]}
    # both pass_rate and the generic mean_score are present for each evaluator
    assert metrics["tool_selection.pass_rate"]["candidate_value"] == 1.0  # right tools
    assert metrics["tool_arguments.pass_rate"]["baseline_value"] == 1.0
    assert metrics["tool_arguments.pass_rate"]["candidate_value"] == 0.0  # wrong args
    assert metrics["tool_arguments.mean_score"]["candidate_value"] == 0.0
    assert any(e["metric"] == "tool_arguments.mean_score" for e in payload["evidence"])

    runs = client.get(f"/experiments/{experiment_id}/runs").json()
    a_run = runs[0]
    assert [c["name"] for c in a_run["tool_calls"]] == ["search", "summarize"]
    assert a_run["tool_calls"][0]["arguments"] in ({"q": "cats"}, {"q": "dogs"})
    assert a_run["tool_calls"][0]["ok"] is True


def test_run_rejects_agent_evaluator_when_case_lacks_labels(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "find cats"}]},
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
                    "parameters": _mock_params(wrong_args=False),
                },
            ).json()["id"]
        )

    experiment_id = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": _version("v1"),
            "candidate_version_id": _version("v2"),
            "repeats": 1,
        },
    ).json()["id"]

    run = client.post(
        f"/experiments/{experiment_id}/run",
        json={"execution": {"backend": "mock"}, "evaluators": [{"type": "tool_selection"}]},
    )
    assert run.status_code == 422
    assert "expected_tool_calls" in run.json()["detail"]
