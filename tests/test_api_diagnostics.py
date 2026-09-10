"""API tests for GET /experiments/{id}/diagnostics.

Deterministic MockProvider only. Diagnostics are explanatory: they must never
change the PASS/BLOCK decision or the metrics from GET /results.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_TEMPLATE = "Q: ${input}"
_RENDERED = "Q: 2+2?"


def _setup(
    client: TestClient,
    *,
    candidate_answer: str = "4",
    candidate_fails: bool = False,
    policy: dict[str, Any] | None = None,
    repeats: int = 2,
) -> str:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={
            "name": "d",
            "version": 1,
            "cases": [{"input": "2+2?", "expected_output": "4"}],
        },
    ).json()["id"]

    def _version(version: str, params: dict[str, Any]) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": _TEMPLATE,
                    "parameters": params,
                },
            ).json()["id"]
        )

    baseline_params = {"mock": {"responses": {_RENDERED: "4"}, "default": "", "latency_ms": 40}}
    candidate_block: dict[str, Any] = {
        "responses": {_RENDERED: candidate_answer},
        "default": "",
        "latency_ms": 40,
    }
    if candidate_fails:
        candidate_block["fail_on"] = [_RENDERED]
    candidate_params = {"mock": candidate_block}

    body: dict[str, Any] = {
        "dataset_id": dataset_id,
        "baseline_version_id": _version("v1", baseline_params),
        "candidate_version_id": _version("v2", candidate_params),
        "repeats": repeats,
    }
    if policy is not None:
        body["release_policy_id"] = client.post("/release-policies", json=policy).json()["id"]
    return str(client.post(f"/projects/{project_id}/experiments", json=body).json()["id"])


def _run(client: TestClient, experiment_id: str) -> Any:
    return client.post(
        f"/experiments/{experiment_id}/run",
        json={"execution": {"backend": "mock"}, "evaluators": [{"type": "contains"}]},
    )


def test_diagnostics_before_first_run_is_available_false(client: TestClient) -> None:
    experiment_id = _setup(client)
    body = client.get(f"/experiments/{experiment_id}/diagnostics").json()

    assert body["available"] is False
    assert body["matched_pairs"] == 0
    assert body["regressing_pairs"] == 0
    assert body["cases"] == []
    assert body["findings"] == []
    assert body["evaluation_result_id"] is None


def test_diagnostics_missing_experiment_is_404(client: TestClient) -> None:
    assert client.get("/experiments/nope/diagnostics").status_code == 404


def test_clean_run_has_no_regressing_cases(client: TestClient) -> None:
    experiment_id = _setup(client)
    _run(client, experiment_id)

    body = client.get(f"/experiments/{experiment_id}/diagnostics").json()
    assert body["available"] is True
    assert body["matched_pairs"] == 2
    assert body["regressing_pairs"] == 0
    assert body["cases"] == []
    assert body["evaluation_result_id"] is not None


def test_evaluator_regression_is_reported_at_case_level(client: TestClient) -> None:
    experiment_id = _setup(client, candidate_answer="wrong", repeats=2)
    _run(client, experiment_id)

    body = client.get(f"/experiments/{experiment_id}/diagnostics").json()
    assert body["available"] is True
    assert body["regressing_pairs"] == 2
    assert body["regressing_cases"] == 1

    categories = {c["category"]: c for c in body["categories"]}
    assert categories["evaluator_regression"]["pairs"] == 2
    assert categories["evaluator_regression"]["cases"] == 1

    (evaluator,) = body["evaluators"]
    assert evaluator["evaluator"] == "contains"
    assert evaluator["pass_to_fail"] == 2

    (case,) = body["cases"]
    assert case["categories"] == ["evaluator_regression"]
    assert case["evaluators"] == ["contains"]
    assert case["provider_failure"] is False
    rep = case["representative"]
    # the representative run ids resolve against GET /runs
    run_ids = {r["id"] for r in client.get(f"/experiments/{experiment_id}/runs").json()}
    assert rep["baseline_run_id"] in run_ids
    assert rep["candidate_run_id"] in run_ids


def test_provider_failure_on_candidate_is_its_own_category(client: TestClient) -> None:
    experiment_id = _setup(client, candidate_fails=True, repeats=1)
    _run(client, experiment_id)

    body = client.get(f"/experiments/{experiment_id}/diagnostics").json()
    categories = {c["category"] for c in body["categories"]}
    assert "provider_execution_failure" in categories
    (case,) = body["cases"]
    assert case["provider_failure"] is True

    finding = next(f for f in body["findings"] if f["kind"] == "provider_failure")
    assert finding["evaluator"] is None
    assert finding["category"] == "provider_execution_failure"


def test_diagnostics_do_not_change_results_decision_or_metrics(client: TestClient) -> None:
    # 8 repeats so the paired-bootstrap guard has enough pairs to confirm the
    # pass-rate regression and actually BLOCK (MIN_PAIRS_TO_BLOCK).
    experiment_id = _setup(
        client,
        candidate_answer="wrong",
        policy={"name": "p", "thresholds": {"contains.pass_rate": 0.1}},
        repeats=8,
    )
    _run(client, experiment_id)

    results_before = client.get(f"/experiments/{experiment_id}/results").json()
    diag = client.get(f"/experiments/{experiment_id}/diagnostics").json()
    results_after = client.get(f"/experiments/{experiment_id}/results").json()

    assert results_before == results_after
    assert results_after[0]["decision"] == "block"
    # diagnostics correlate with, but never produce, that decision
    assert diag["evaluation_result_id"] == results_after[0]["id"]
    assert diag["regressing_pairs"] == 8
