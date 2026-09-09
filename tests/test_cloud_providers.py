"""Tests for evalops.cloud_providers (OpenAIProvider / AnthropicProvider).

No real network, no real API keys: ``urllib.request.urlopen`` is monkeypatched
exactly as in ``test_ollama_provider.py``, and the key env vars are set to
throwaway strings that are never sent anywhere real.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from evalops.cloud_providers import (
    AnthropicProvider,
    OpenAIProvider,
    cloud_params,
    require_api_key,
)
from evalops.domain.contracts import ProviderClient, ProviderError, ProviderResponse
from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError


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


@pytest.fixture(autouse=True)
def _fake_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")


def _sv(provider: ProviderName, *, model: str = "m", parameters: Any = None) -> SystemVersion:
    return SystemVersion(
        project_id="p",
        name="cfg",
        version="v",
        provider=provider,
        model=model,
        prompt_template="Q: ${input}",
        parameters=parameters or {},
    )


def _openai_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "choices": [{"message": {"role": "assistant", "content": "Paris"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
    }
    body.update(overrides)
    return body


def _anthropic_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "content": [{"type": "text", "text": "Paris"}],
        "usage": {"input_tokens": 20, "output_tokens": 4},
        "stop_reason": "end_turn",
    }
    body.update(overrides)
    return body


# --- contract ------------------------------------------------------------


def test_providers_satisfy_the_protocol() -> None:
    assert isinstance(OpenAIProvider(), ProviderClient)
    assert isinstance(AnthropicProvider(), ProviderClient)
    assert OpenAIProvider.name == "openai"
    assert AnthropicProvider.name == "anthropic"


def test_provider_object_never_holds_the_key() -> None:
    text = repr(OpenAIProvider()) + repr(AnthropicProvider())
    assert "not-a-real-key" not in text
    assert "API_KEY" not in text


# --- OpenAI: request + success + usage ---------------------------------


def test_openai_request_shape_and_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_openai_body()))

    OpenAIProvider().complete("Q: hi", _sv(ProviderName.OPENAI, model="gpt-4o-mini"))

    request = urlopen.request
    assert request.full_url == "https://api.openai.com/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer sk-test-not-a-real-key"
    sent = json.loads(request.data)
    assert sent["model"] == "gpt-4o-mini"
    assert sent["messages"] == [{"role": "user", "content": "Q: hi"}]
    assert urlopen.timeout == 120.0


def test_openai_success_maps_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body=_openai_body()))

    response = OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))

    assert isinstance(response, ProviderResponse)
    assert response.text == "Paris"
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 3
    assert response.usage.cost_usd == 0.0  # never fabricated
    assert response.usage.latency_ms >= 0.0  # client-measured


def test_openai_missing_usage_yields_zero_not_a_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _openai_body()
    del body["usage"]
    _install(monkeypatch, _Urlopen(body=body))

    response = OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))

    assert response.text == "Paris"
    assert (response.usage.prompt_tokens, response.usage.completion_tokens) == (0, 0)


def test_openai_generation_parameters_are_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_openai_body()))
    params = {"temperature": 0.0, "max_tokens": 64, "top_p": 0.9}

    OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI, parameters=params))

    sent = json.loads(urlopen.request.data)
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == 64
    assert sent["top_p"] == 0.9


# --- OpenAI: failures -> ProviderError --------------------------------


def test_openai_http_error_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError(
        url="https://api.openai.com/v1/chat/completions",
        code=429,
        msg="Too Many Requests",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    _install(monkeypatch, _Urlopen(error=err))

    with pytest.raises(ProviderError, match="HTTP 429"):
        OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))


def test_openai_connection_error_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(error=urllib.error.URLError("Connection refused")))

    with pytest.raises(ProviderError, match="chat/completions"):
        OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))


def test_openai_malformed_body_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body={"choices": []}))

    with pytest.raises(ProviderError, match="no choices"):
        OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))


def test_openai_rejects_a_non_openai_system_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body=_openai_body()))

    with pytest.raises(ProviderError, match="requires a SystemVersion with provider 'openai'"):
        OpenAIProvider().complete("hi", _sv(ProviderName.ANTHROPIC))


# --- Anthropic: request + success + usage -----------------------------


def test_anthropic_request_shape_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_anthropic_body()))

    AnthropicProvider().complete("Q: hi", _sv(ProviderName.ANTHROPIC, model="claude-3-5-haiku"))

    request = urlopen.request
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.get_header("X-api-key") == "sk-ant-test-not-a-real-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    sent = json.loads(request.data)
    assert sent["model"] == "claude-3-5-haiku"
    assert sent["messages"] == [{"role": "user", "content": "Q: hi"}]
    assert sent["max_tokens"] == 1024  # API requires it; default injected


def test_anthropic_success_maps_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        _Urlopen(
            body=_anthropic_body(
                content=[{"type": "text", "text": "Par"}, {"type": "text", "text": "is"}]
            )
        ),
    )

    response = AnthropicProvider().complete("hi", _sv(ProviderName.ANTHROPIC))

    assert response.text == "Paris"  # text blocks concatenated
    assert response.usage.prompt_tokens == 20
    assert response.usage.completion_tokens == 4
    assert response.usage.cost_usd == 0.0


def test_anthropic_explicit_max_tokens_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    urlopen = _install(monkeypatch, _Urlopen(body=_anthropic_body()))

    AnthropicProvider().complete(
        "hi", _sv(ProviderName.ANTHROPIC, parameters={"max_tokens": 256, "temperature": 0.0})
    )

    sent = json.loads(urlopen.request.data)
    assert sent["max_tokens"] == 256
    assert sent["temperature"] == 0.0


def test_anthropic_http_error_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/messages",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    _install(monkeypatch, _Urlopen(error=err))

    with pytest.raises(ProviderError, match="HTTP 401"):
        AnthropicProvider().complete("hi", _sv(ProviderName.ANTHROPIC))


def test_anthropic_no_text_block_becomes_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _Urlopen(body=_anthropic_body(content=[{"type": "tool_use"}])))

    with pytest.raises(ProviderError, match="no text content block"):
        AnthropicProvider().complete("hi", _sv(ProviderName.ANTHROPIC))


# --- missing API key ---------------------------------------------------


def test_missing_openai_key_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install(monkeypatch, _Urlopen(body=_openai_body()))

    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        OpenAIProvider().complete("hi", _sv(ProviderName.OPENAI))


def test_blank_anthropic_key_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider().complete("hi", _sv(ProviderName.ANTHROPIC))


def test_require_api_key_is_a_noop_for_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    require_api_key(ProviderName.OLLAMA)  # no raise
    with pytest.raises(ConfigError):
        require_api_key(ProviderName.OPENAI)


# --- parameter allowlist --------------------------------------------


def test_cloud_params_rejects_unknown_and_bad_values() -> None:
    with pytest.raises(ConfigError, match="not a supported OpenAI generation parameter"):
        cloud_params({"frequency_penalty": 0.1}, provider="OpenAI")
    with pytest.raises(ConfigError, match="must be an integer >= 1"):
        cloud_params({"max_tokens": 0}, provider="Anthropic")
    with pytest.raises(ConfigError, match="must be a number >= 0"):
        cloud_params({"temperature": -1}, provider="OpenAI")
    assert cloud_params({"mock": {"x": 1}, "temperature": 0.2}, provider="OpenAI") == {
        "temperature": 0.2
    }
