"""API: RAG retrieval evidence + labels round-trip through the existing
dataset / run / results endpoints (Phase 9, CP 9.1). MockProvider only.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_TEMPLATE = "Q: ${input}"


def _mock_params(*, drop_relevant: bool) -> dict[str, Any]:
    items = [{"doc_id": "d1", "content": "Paris is the capital of France", "rank": 0}]
    if not drop_relevant:
        items.append({"doc_id": "d2", "content": "France is in Europe", "rank": 1})
    return {
        "mock": {
            "responses": {"Q: capital of France": "Paris"},
            "retrieval": {"Q: capital of France": items},
            "latency_ms": 5,
        }
    }


def test_dataset_expected_retrieval_ids_round_trip(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    created = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "rag",
            "version": 1,
            "cases": [
                {"input": "capital of France", "expected_retrieval_ids": ["d1", "d2"]},
                {"input": "plain", "expected_output": "x"},
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["cases"][0]["expected_retrieval_ids"] == ["d1", "d2"]
    assert body["cases"][1]["expected_retrieval_ids"] == []

    fetched = client.get(f"/datasets/{body['id']}")
    assert fetched.json() == body


def test_run_exposes_retrieval_evidence_and_rag_metrics(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "rag",
            "version": 1,
            "cases": [{"input": "capital of France", "expected_retrieval_ids": ["d1", "d2"]}],
        },
    ).json()["id"]

    def _version(version: str, *, drop: bool) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": _TEMPLATE,
                    "parameters": _mock_params(drop_relevant=drop),
                },
            ).json()["id"]
        )

    experiment_id = client.post(
        f"/projects/{project_id}/experiments",
        json={
            "dataset_id": dataset_id,
            "baseline_version_id": _version("v1", drop=False),
            "candidate_version_id": _version("v2", drop=True),
            "repeats": 2,
        },
    ).json()["id"]

    run = client.post(
        f"/experiments/{experiment_id}/run",
        json={
            "execution": {"backend": "mock"},
            "evaluators": [{"type": "retrieval_recall", "min_recall": 1.0}],
        },
    )
    assert run.status_code == 201
    payload = run.json()
    metrics = {m["metric"]: m for m in payload["metrics"]}
    assert metrics["retrieval_recall.pass_rate"]["baseline_value"] == 1.0
    assert metrics["retrieval_recall.pass_rate"]["candidate_value"] == 0.0
    assert any(e["metric"] == "retrieval_recall.pass_rate" for e in payload["evidence"])

    runs = client.get(f"/experiments/{experiment_id}/runs").json()
    baseline_run = next(r for r in runs if len(r["retrieval"]) == 2)
    assert {i["doc_id"] for i in baseline_run["retrieval"]} == {"d1", "d2"}
    assert baseline_run["retrieval"][0]["rank"] == 0
    candidate_run = next(r for r in runs if len(r["retrieval"]) == 1)
    assert candidate_run["retrieval"][0]["doc_id"] == "d1"


def test_run_rejects_rag_evaluator_when_case_lacks_labels(client: TestClient) -> None:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "capital of France"}]},
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
                    "parameters": _mock_params(drop_relevant=False),
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
        json={
            "execution": {"backend": "mock"},
            "evaluators": [{"type": "retrieval_recall"}],
        },
    )
    # the evaluator raises ConfigError -> 422 via the registered handler
    assert run.status_code == 422
    assert "expected_retrieval_ids" in run.json()["detail"]
