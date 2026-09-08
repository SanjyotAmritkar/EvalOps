"""Tests for evalops.providers.MockProvider."""

from __future__ import annotations

from typing import Any

import pytest

from evalops.domain.contracts import ProviderClient, ProviderError, ProviderResponse
from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.providers import MockProvider


def _sv(mock: Any = None) -> SystemVersion:
    parameters: dict[str, Any] = {} if mock is None else {"mock": mock}
    return SystemVersion(
        project_id="p",
        name="cfg",
        version="v1",
        provider=ProviderName.OPENAI,
        model="m",
        prompt_template="Q: ${input}",
        parameters=parameters,
    )


def test_satisfies_provider_client_protocol() -> None:
    client: ProviderClient = MockProvider()

    assert isinstance(client, ProviderClient)
    assert MockProvider.name == "mock"


def test_exact_prompt_lookup() -> None:
    sv = _sv({"responses": {"Q: 2 + 2 = ?": "4"}})

    assert MockProvider().complete("Q: 2 + 2 = ?", sv).text == "4"


def test_default_response_when_prompt_not_found() -> None:
    sv = _sv({"responses": {"known": "yes"}, "default": "idk"})

    assert MockProvider().complete("unknown prompt", sv).text == "idk"


def test_default_is_empty_string_when_unset() -> None:
    assert MockProvider().complete("anything", _sv({"responses": {}})).text == ""


def test_missing_mock_block_is_treated_as_empty_config() -> None:
    response = MockProvider().complete("anything", _sv(None))

    assert response.text == ""


def test_substring_prompts_do_not_accidentally_match() -> None:
    sv = _sv({"responses": {"Q: 2 + 2 = ?": "4"}, "default": "MISS"})
    provider = MockProvider()

    assert provider.complete("2 + 2", sv).text == "MISS"
    assert provider.complete("Q: 2 + 2 = ? and more", sv).text == "MISS"


def test_same_inputs_produce_an_equal_response() -> None:
    sv = _sv({"responses": {"p": "hello world"}, "latency_ms": 40})
    provider = MockProvider()

    assert provider.complete("p", sv) == provider.complete("p", sv)


def test_usage_metrics_are_deterministic_synthetic_values() -> None:
    sv = _sv({"responses": {"a b c": "x y"}, "latency_ms": 40})

    usage = MockProvider().complete("a b c", sv).usage

    assert usage.prompt_tokens == 3
    assert usage.completion_tokens == 2
    assert usage.total_tokens == 5
    assert usage.latency_ms == 40.0
    assert usage.cost_usd == 0.0


def test_fail_on_raises_provider_error_for_listed_prompt_only() -> None:
    sv = _sv({"responses": {"ok": "fine"}, "fail_on": ["boom"]})
    provider = MockProvider()

    with pytest.raises(ProviderError):
        provider.complete("boom", sv)
    assert provider.complete("ok", sv).text == "fine"


def test_complete_returns_a_provider_response() -> None:
    assert isinstance(MockProvider().complete("x", _sv({})), ProviderResponse)


@pytest.mark.parametrize(
    "mock",
    [
        "not a mapping",
        {"responses": ["not", "a", "map"]},
        {"responses": {"k": 5}},
        {"default": 7},
        {"latency_ms": -1},
        {"latency_ms": True},
        {"fail_on": "boom"},
        {"fail_on": [1, 2]},
        {"unexpected": 1},
    ],
)
def test_malformed_mock_config_raises_config_error(mock: Any) -> None:
    with pytest.raises(ConfigError):
        MockProvider().complete("x", _sv(mock))
