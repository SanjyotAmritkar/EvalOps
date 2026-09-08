"""Tests for evalops.ollama (OllamaProvider) -- no real network.

Ollama HTTP calls are intercepted by monkeypatching ``urllib.request.urlopen``.
"""

from __future__ import annotations

import email.message
import io
import json
import urllib.error
from typing import Any

import pytest

from evalops.domain.contracts import ProviderClient, ProviderError, ProviderResponse
from evalops.domain.entities import Dataset, DatasetCase, EvaluationRun, Experiment, SystemVersion
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.evaluators import RegexMatch
from evalops.ollama import OllamaProvider, build_options
from evalops.runner import run_experiment


class _FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Urlopen:
    """Stand-in for urllib.request.urlopen that records the request."""

    def __init__(
        self, *, body: Any = None, raw: bytes | None = None, error: BaseException | None = None
    ) -> None:
        self._body = body
        self._raw = raw
        self._error = error
        self.request: Any = None
        self.timeout: float | None = None

    def __call__(self, request: Any, timeout: float | None = None) -> _FakeHTTPResponse:
        self.request = request
        self.timeout = timeout
        if self._error is not None:
            raise self._error
        payload = self._raw if self._raw is not None else json.dumps(self._body).encode("utf-8")
        return _FakeHTTPResponse(payload)


def _install(monkeypatch: pytest.MonkeyPatch, urlopen: _Urlopen) -> _Urlopen:
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return urlopen


def _ok_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "response": "Paris",
        "prompt_eval_count": 11,
        "eval_count": 3,
        "total_duration": 1_500_000_000,  # 1.5 s, in nanoseconds
        "done": True,
    }
    body.update(overrides)
    return body


def _sv(
    *, provider: ProviderName = ProviderName.OLLAMA, model: str = "llama3.2", parameters: Any = None
) -> SystemVersion:
    return SystemVersion(
        project_id="p",
        name="cfg",
        version="v",
        provider=provider,
        model=model,
        prompt_template="Q: ${input}",
        parameters=parameters or {},
    )


# --- contract ---------------------------------------------------------------


def test_satisfies_provider_client_protocol() -> None:
    client: ProviderClient = OllamaProvider()

    assert isinstance(client, ProviderClient)
    assert OllamaProvider.name == "ollama"


# --- request construction --------------------------------------------------


def test_request_url_method_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_ok_body()))

    OllamaProvider().complete("Q: hi", _sv())

    request = urlopen.request
    assert request.full_url == "http://localhost:11434/api/generate"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"model": "llama3.2", "prompt": "Q: hi", "stream": False}
    assert urlopen.timeout == 120.0


def test_base_url_trailing_slash_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_ok_body()))

    OllamaProvider(base_url="http://localhost:11434/").complete("hi", _sv())

    assert urlopen.request.full_url == "http://localhost:11434/api/generate"


def test_allowed_generation_parameters_map_to_options(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_ok_body()))
    params = {"temperature": 0.2, "seed": 7, "top_p": 0.9, "num_predict": 32}

    OllamaProvider().complete("hi", _sv(parameters=params))

    assert json.loads(urlopen.request.data)["options"] == params


def test_mock_only_block_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_ok_body()))
    params = {"mock": {"responses": {}, "latency_ms": 5}, "temperature": 0.0}

    OllamaProvider().complete("hi", _sv(parameters=params))

    body = json.loads(urlopen.request.data)
    assert body["options"] == {"temperature": 0.0}
    assert "mock" not in json.dumps(body)


def test_build_options_rejects_unsupported_and_bad_values() -> None:
    with pytest.raises(ConfigError, match="not a supported Ollama generation parameter"):
        build_options({"frequency_penalty": 0.1})
    with pytest.raises(ConfigError, match="must be an integer"):
        build_options({"seed": "nope"})
    with pytest.raises(ConfigError, match="must be a number"):
        build_options({"temperature": -1})


# --- response parsing ----------------------------------------------------


def test_response_text_and_real_usage_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body=_ok_body(response="Paris", total_duration=250_000_000)))

    response = OllamaProvider().complete("hi", _sv())

    assert isinstance(response, ProviderResponse)
    assert response.text == "Paris"
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 3
    assert response.usage.latency_ms == 250.0  # 250_000_000 ns
    assert response.usage.cost_usd == 0.0


# --- failures -> ProviderError -----------------------------------------


def test_connection_failure_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(error=urllib.error.URLError("Connection refused")))

    with pytest.raises(ProviderError, match="http://localhost:11434/api/generate"):
        OllamaProvider().complete("hi", _sv())


def test_timeout_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(error=TimeoutError("timed out")))

    with pytest.raises(ProviderError, match="timed out"):
        OllamaProvider(timeout_seconds=5).complete("hi", _sv())


def test_http_non_2xx_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError(
        "http://localhost:11434/api/generate",
        500,
        "Server Error",
        email.message.Message(),
        io.BytesIO(b"boom"),
    )
    _install(monkeypatch, _Urlopen(error=err))

    with pytest.raises(ProviderError, match="HTTP 500"):
        OllamaProvider().complete("hi", _sv())


def test_malformed_json_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(raw=b"not json at all"))

    with pytest.raises(ProviderError, match="non-JSON"):
        OllamaProvider().complete("hi", _sv())


def test_ollama_error_payload_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body={"error": "model 'llama3.2' not found"}))

    with pytest.raises(ProviderError, match="Ollama error"):
        OllamaProvider().complete("hi", _sv())


def test_missing_response_text_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _ok_body()
    del body["response"]
    _install(monkeypatch, _Urlopen(body=body))

    with pytest.raises(ProviderError, match="missing 'response' text"):
        OllamaProvider().complete("hi", _sv())


@pytest.mark.parametrize("missing", ["prompt_eval_count", "eval_count", "total_duration"])
def test_missing_usage_metadata_becomes_provider_error(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    body = _ok_body()
    del body[missing]
    _install(monkeypatch, _Urlopen(body=body))

    with pytest.raises(ProviderError, match="missing or invalid"):
        OllamaProvider().complete("hi", _sv())


def test_non_ollama_system_version_is_rejected_before_any_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_ok_body()))

    with pytest.raises(ProviderError, match="requires a SystemVersion with provider 'ollama'"):
        OllamaProvider().complete("hi", _sv(provider=ProviderName.OPENAI))
    assert urlopen.request is None  # no request was attempted


# --- runner integration (unchanged engine) --------------------------


def test_flows_through_the_existing_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body=_ok_body(response="42", total_duration=2_000_000)))
    baseline = _sv()
    candidate = _sv(model="llama3.2-mini")
    dataset = Dataset(
        project_id="p",
        name="d",
        version=1,
        cases=(DatasetCase(input="q", expected_output="42", id="c0"),),
    )
    experiment = Experiment(
        project_id="p",
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
    )

    outcome = run_experiment(
        experiment,
        dataset,
        baseline,
        candidate,
        providers={ProviderName.OLLAMA: OllamaProvider()},
        evaluators=[RegexMatch(pattern=r"\d")],
    )

    run = outcome.runs[0]
    assert isinstance(run, EvaluationRun)
    assert run.output == "42"
    assert run.usage.prompt_tokens == 11
    assert run.usage.latency_ms == 2.0  # 2_000_000 ns
