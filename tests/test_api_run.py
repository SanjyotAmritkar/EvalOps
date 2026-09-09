"""API execution tests: POST /experiments/{id}/run end to end, plus the read
endpoints. Deterministic MockProvider only -- no Ollama, no PostgreSQL.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_TEMPLATE = "Q: ${input}"
_CASE_INPUT = "2+2?"
_RENDERED = "Q: 2+2?"


def _mock_params(*, latency: float, fail: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"responses": {_RENDERED: "4"}, "default": "", "latency_ms": latency}
    if fail:
        block["fail_on"] = [_RENDERED]
    return {"mock": block}


def _setup(
    client: TestClient,
    *,
    baseline_latency: float = 40,
    candidate_latency: float = 40,
    candidate_fails: bool = False,
    policy: dict[str, Any] | None = None,
    expected_output: str | None = "4",
) -> str:
    """Create project/dataset/versions/experiment; return the experiment id."""
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    case: dict[str, Any] = {"input": _CASE_INPUT}
    if expected_output is not None:
        case["expected_output"] = expected_output
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [case]},
    ).json()["id"]

    def _version(version: str, latency: float, fail: bool) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": _TEMPLATE,
                    "parameters": _mock_params(latency=latency, fail=fail),
                },
            ).json()["id"]
        )

    baseline_id = _version("v1", baseline_latency, False)
    candidate_id = _version("v2", candidate_latency, candidate_fails)

    body: dict[str, Any] = {
        "dataset_id": dataset_id,
        "baseline_version_id": baseline_id,
        "candidate_version_id": candidate_id,
        "repeats": 2,
    }
    if policy is not None:
        policy_id = client.post("/release-policies", json=policy).json()["id"]
        body["release_policy_id"] = policy_id
    return str(client.post(f"/projects/{project_id}/experiments", json=body).json()["id"])


def _run(client: TestClient, experiment_id: str, evaluators: list[dict[str, Any]]) -> Any:
    return client.post(
        f"/experiments/{experiment_id}/run",
        json={"execution": {"backend": "mock"}, "evaluators": evaluators},
    )


# --- happy paths ------------------------------------------------------------


def test_run_pass_end_to_end_and_persists(client: TestClient) -> None:
    experiment_id = _setup(client, policy={"name": "p", "thresholds": {"latency_ms.p95": 0.2}})

    response = _run(client, experiment_id, [{"type": "contains", "case_sensitive": False}])
    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "pass"
    assert body["gated"] is True
    assert body["counts"] == {
        "cases": 1,
        "runs": 4,
        "failures": 0,
    }  # 2 versions x 1 case x 2 repeats
    assert body["evaluation_result_id"]
    assert {m["metric"] for m in body["metrics"]} >= {
        "success_rate",
        "contains.pass_rate",
        "latency_ms.p95",
    }

    runs = client.get(f"/experiments/{experiment_id}/runs").json()
    assert len(runs) == 4
    assert all(run["usage"]["total_tokens"] >= 0 for run in runs)
    assert all(run["scores"][0]["evaluator"] == "contains" for run in runs)

    results = client.get(f"/experiments/{experiment_id}/results").json()
    assert len(results) == 1
    assert results[0]["id"] == body["evaluation_result_id"]
    assert any(m["metric"] == "latency_ms.p95" for m in results[0]["metrics"])


def test_run_block_on_latency_regression(client: TestClient) -> None:
    experiment_id = _setup(
        client,
        baseline_latency=40,
        candidate_latency=80,
        policy={"name": "p", "thresholds": {"latency_ms.p95": 0.2}},
    )

    body = _run(client, experiment_id, [{"type": "contains"}]).json()

    assert body["decision"] == "block"
    assert any("latency_ms.p95" in reason for reason in body["reasons"])


def test_run_ungated_when_no_policy(client: TestClient) -> None:
    experiment_id = _setup(client)  # no release policy
    body = _run(client, experiment_id, [{"type": "contains"}]).json()

    assert body["gated"] is False
    assert body["decision"] == "pass"


# --- persisted release decision (G-1): recomputed on GET /results ----------


def test_results_recompute_pass_decision_on_read(client: TestClient) -> None:
    experiment_id = _setup(client, policy={"name": "p", "thresholds": {"latency_ms.p95": 0.5}})
    run_body = _run(client, experiment_id, [{"type": "contains"}]).json()

    results = client.get(f"/experiments/{experiment_id}/results").json()
    assert len(results) == 1
    result = results[0]
    assert result["decision"] == "pass"
    assert result["gated"] is True
    assert result["reasons"] == []
    gated_line = next(m for m in result["metrics"] if m["metric"] == "latency_ms.p95")
    assert gated_line["threshold"] == 0.5
    assert gated_line["regression"] is False
    assert gated_line["direction"] == "lower_is_better"
    # the read decision is identical to the synchronous run response
    assert result["decision"] == run_body["decision"]
    assert result["reasons"] == run_body["reasons"]


def test_results_recompute_block_decision_on_read(client: TestClient) -> None:
    experiment_id = _setup(
        client,
        baseline_latency=40,
        candidate_latency=80,
        policy={"name": "p", "thresholds": {"latency_ms.p95": 0.2}},
    )
    run_body = _run(client, experiment_id, [{"type": "contains"}]).json()
    assert run_body["decision"] == "block"

    results = client.get(f"/experiments/{experiment_id}/results").json()
    result = results[0]
    assert result["decision"] == "block"
    assert result["reasons"] == run_body["reasons"]
    assert any("latency_ms.p95" in reason for reason in result["reasons"])
    blocking = [m for m in result["metrics"] if m["regression"]]
    assert [m["metric"] for m in blocking] == ["latency_ms.p95"]
    assert blocking[0]["adverse_change"] is not None
    assert blocking[0]["threshold"] == 0.2


def test_results_ungated_when_experiment_has_no_policy(client: TestClient) -> None:
    experiment_id = _setup(client)  # no policy
    _run(client, experiment_id, [{"type": "contains"}])

    result = client.get(f"/experiments/{experiment_id}/results").json()[0]
    assert result["gated"] is False
    assert result["decision"] == "pass"
    assert result["reasons"] == []
    assert all(m["threshold"] is None for m in result["metrics"])
    assert all(m["regression"] is False for m in result["metrics"])


def test_results_empty_list_before_first_run(client: TestClient) -> None:
    experiment_id = _setup(client, policy={"name": "p", "thresholds": {"latency_ms.p95": 0.2}})
    response = client.get(f"/experiments/{experiment_id}/results")
    assert response.status_code == 200
    assert response.json() == []


# --- provider failure handling -----------------------------------------


def test_provider_failure_is_recorded_not_a_500(client: TestClient) -> None:
    experiment_id = _setup(
        client,
        candidate_fails=True,
        policy={"name": "p", "thresholds": {"success_rate": 0.0}},
    )

    response = _run(client, experiment_id, [{"type": "contains"}])

    assert response.status_code == 201  # not a server error
    body = response.json()
    assert body["counts"]["failures"] == 2  # candidate's case fails on both repeats
    assert body["decision"] == "block"  # success_rate dropped below the (0%) tolerance

    runs = client.get(f"/experiments/{experiment_id}/runs").json()
    failed = [run for run in runs if run["error"] is not None]
    assert len(failed) == 2
    assert all(run["scores"] == [] for run in failed)


# --- conflicts and missing resources ---------------------------------


def test_repeated_execution_is_409_and_does_not_overwrite(client: TestClient) -> None:
    experiment_id = _setup(client)

    first = _run(client, experiment_id, [{"type": "contains"}])
    assert first.status_code == 201
    runs_after_first = client.get(f"/experiments/{experiment_id}/runs").json()

    second = _run(client, experiment_id, [{"type": "contains"}])
    assert second.status_code == 409
    assert "already been run" in second.json()["detail"]

    assert client.get(f"/experiments/{experiment_id}/runs").json() == runs_after_first
    assert len(client.get(f"/experiments/{experiment_id}/results").json()) == 1


def test_run_missing_experiment_is_404(client: TestClient) -> None:
    assert _run(client, "nope", [{"type": "contains"}]).status_code == 404


def test_runs_and_results_for_missing_experiment_are_404(client: TestClient) -> None:
    assert client.get("/experiments/nope/runs").status_code == 404
    assert client.get("/experiments/nope/results").status_code == 404


# --- request validation ---------------------------------------------


def test_run_without_evaluators_is_422(client: TestClient) -> None:
    experiment_id = _setup(client)
    response = client.post(
        f"/experiments/{experiment_id}/run",
        json={"execution": {"backend": "mock"}, "evaluators": []},
    )
    assert response.status_code == 422


def test_run_with_invalid_evaluator_spec_is_422(client: TestClient) -> None:
    experiment_id = _setup(client)
    missing_pattern = _run(client, experiment_id, [{"type": "regex_match"}])
    assert missing_pattern.status_code == 422

    experiment_id_2 = _setup(client)
    unknown_type = _run(client, experiment_id_2, [{"type": "bogus"}])
    assert unknown_type.status_code == 422


def test_exact_match_without_expected_output_is_422_and_persists_nothing(
    client: TestClient,
) -> None:
    experiment_id = _setup(client, expected_output=None)

    response = _run(client, experiment_id, [{"type": "exact_match"}])

    assert response.status_code == 422
    assert client.get(f"/experiments/{experiment_id}/runs").json() == []
