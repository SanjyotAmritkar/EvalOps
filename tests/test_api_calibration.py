"""API: POST /judge-calibrations (run) and GET /judge-calibrations/{id} (retrieve).

The judge provider is a stubbed OpenAI HTTP endpoint (``urllib.request.urlopen``
monkeypatched); the key env var is a throwaway string. No network, no credits.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

_FAKE_KEY = "sk-test-not-a-real-key"


class _FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _stub_openai(monkeypatch: pytest.MonkeyPatch, *, judge_replies: list[str]) -> None:
    """Return one OpenAI chat-completion per call, wrapping the next judge reply."""
    queue = list(judge_replies)

    def _fake(_request: Any, timeout: float | None = None) -> _FakeHTTPResponse:
        text = queue.pop(0) if queue else '{"verdict": "pass"}'
        body = {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        return _FakeHTTPResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", _fake)


def _example(human_pass: bool, *, out: str = "answer") -> dict[str, Any]:
    return {"input": "q", "output": out, "human_pass": human_pass}


def _create(client: TestClient, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "name": "correctness",
        "examples": [_example(True), _example(False), _example(True)],
    }
    body.update(overrides)
    return client.post("/judge-calibrations", json=body)


# --- run + retrieve --------------------------------------------------


def test_create_runs_the_judge_and_persists_metrics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    _stub_openai(
        monkeypatch,
        judge_replies=[
            '{"verdict": "pass", "score": 0.9, "reasoning": "correct"}',
            '{"verdict": "fail", "score": 0.1}',
            '{"verdict": "fail", "score": 0.2}',  # disagrees with human pass -> FN
        ],
    )

    response = _create(client)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["judge_provider"] == "openai"
    assert body["judge_model"] == "gpt-4o-mini"
    assert body["judge_name"] == "correctness"
    assert body["rubric_id"] == "judge-v1"
    m = body["metrics"]
    assert (m["total"], m["scored"], m["failures"]) == (3, 3, 0)
    assert (m["true_positives"], m["true_negatives"], m["false_negatives"]) == (1, 1, 1)
    assert m["agreement_rate"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(0.5)
    assert len(body["cases"]) == 3
    assert body["cases"][0]["judge_reasoning"] == "correct"

    # retrieve the persisted result -- identical
    got = client.get(f"/judge-calibrations/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body


def test_no_secret_is_persisted_or_returned(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    _stub_openai(monkeypatch, judge_replies=['{"verdict": "pass"}'] * 3)

    created = _create(client).json()
    fetched = client.get(f"/judge-calibrations/{created['id']}").text

    for blob in (json.dumps(created), fetched):
        assert _FAKE_KEY not in blob
        assert "api_key" not in blob.lower()
        assert "authorization" not in blob.lower()


def test_judge_failure_is_recorded_not_a_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    _stub_openai(
        monkeypatch,
        judge_replies=['{"verdict": "pass"}', "not json at all", '{"verdict": "fail"}'],
    )

    response = _create(client)

    assert response.status_code == 201  # calibration completes; failure is data
    body = response.json()
    assert body["metrics"]["failures"] == 1
    assert body["metrics"]["scored"] == 2
    failed = body["cases"][1]
    assert failed["judge_pass"] is None
    assert "JudgeError" in (failed["error"] or "")


# --- errors --------------------------------------------------------


def test_missing_api_key_is_a_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = _create(client)

    assert response.status_code == 422
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_unknown_provider_is_a_422(client: TestClient) -> None:
    assert _create(client, provider="cohere").status_code == 422


def test_empty_examples_list_is_a_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    assert _create(client, examples=[]).status_code == 422


def test_retrieve_unknown_calibration_is_404(client: TestClient) -> None:
    assert client.get("/judge-calibrations/does-not-exist").status_code == 404
