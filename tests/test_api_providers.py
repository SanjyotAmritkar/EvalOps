"""API surface for CP 6.1: cross-provider execution backends and the llm_judge
evaluator, exercised through ``POST /experiments/{id}/run``.

No real network or keys: ``urllib.request.urlopen`` is stubbed and the key env
vars are throwaway strings.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient


class _FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _stub_urlopen(monkeypatch: pytest.MonkeyPatch, *, openai_text: str) -> None:
    body = {
        "choices": [{"message": {"role": "assistant", "content": openai_text}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    payload = json.dumps(body).encode("utf-8")

    def _fake(_request: Any, timeout: float | None = None) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", _fake)


def _setup(
    client: TestClient,
    *,
    baseline_provider: str = "openai",
    candidate_provider: str = "openai",
    baseline_model: str = "gpt-4o-mini",
    candidate_model: str = "gpt-4o",
) -> str:
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "2+2?", "expected_output": "4"}]},
    ).json()["id"]

    def _version(provider: str, model: str, version: str) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": provider,
                    "model": model,
                    "prompt_template": "Q: ${input}",
                    "parameters": {"temperature": 0.0},
                },
            ).json()["id"]
        )

    return str(
        client.post(
            f"/projects/{project_id}/experiments",
            json={
                "dataset_id": dataset_id,
                "baseline_version_id": _version(baseline_provider, baseline_model, "v1"),
                "candidate_version_id": _version(candidate_provider, candidate_model, "v2"),
                "repeats": 1,
            },
        ).json()["id"]
    )


def _run(client: TestClient, experiment_id: str, body: dict[str, Any]) -> Any:
    return client.post(f"/experiments/{experiment_id}/run", json=body)


# --- hosted backend selection ----------------------------------------


def test_openai_backend_without_a_key_is_a_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    experiment_id = _setup(client)

    response = _run(
        client,
        experiment_id,
        {"execution": {"backend": "openai"}, "evaluators": [{"type": "contains"}]},
    )

    assert response.status_code == 422
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_live_backend_runs_a_hosted_experiment_end_to_end(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _stub_urlopen(monkeypatch, openai_text="4")
    experiment_id = _setup(client, baseline_model="gpt-4o-mini", candidate_model="gpt-4o")

    response = _run(
        client,
        experiment_id,
        {
            "execution": {"backend": "live"},
            "evaluators": [{"type": "contains", "case_sensitive": False}],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] in {"pass", "block"}
    assert body["counts"] == {"cases": 1, "runs": 2, "failures": 0}
    metrics = {m["metric"] for m in body["metrics"]}
    assert {"success_rate", "contains.pass_rate"} <= metrics


# --- llm_judge evaluator, independent of the system under test ------


def test_llm_judge_scores_a_mock_system_via_a_hosted_judge(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _stub_urlopen(monkeypatch, openai_text='{"verdict": "pass", "score": 0.9}')
    # system under test is the deterministic mock; the judge is OpenAI.
    experiment_id = _setup(client, baseline_provider="openai", candidate_provider="openai")

    response = _run(
        client,
        experiment_id,
        {
            "execution": {"backend": "mock"},
            "evaluators": [{"type": "llm_judge", "provider": "openai", "model": "gpt-4o-mini"}],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert any(m["metric"] == "llm_judge.pass_rate" for m in body["metrics"])
    judged = next(m for m in body["metrics"] if m["metric"] == "llm_judge.pass_rate")
    assert judged["candidate_value"] == 1.0  # judge said pass on both runs


def test_malformed_judge_output_is_a_502_not_a_silent_pass(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _stub_urlopen(monkeypatch, openai_text="I think it looks fine to me!")
    experiment_id = _setup(client)

    response = _run(
        client,
        experiment_id,
        {
            "execution": {"backend": "mock"},
            "evaluators": [{"type": "llm_judge", "provider": "openai", "model": "gpt-4o-mini"}],
        },
    )

    assert response.status_code == 502
    assert "judge" in response.json()["detail"].lower()
