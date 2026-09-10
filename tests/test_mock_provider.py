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


# --- retrieval evidence (Phase 9) ------------------------------------


def test_no_retrieval_by_default() -> None:
    assert MockProvider().complete("x", _sv({"responses": {"x": "y"}})).retrieval == ()


def test_deterministic_retrieval_evidence_per_prompt() -> None:
    sv = _sv(
        {
            "responses": {"Q: k": "a"},
            "retrieval": {
                "Q: k": [
                    {"doc_id": "d2", "content": "second", "rank": 1, "score": 0.4},
                    {"doc_id": "d1", "content": "first", "rank": 0},
                ]
            },
        }
    )
    first = MockProvider().complete("Q: k", sv).retrieval
    second = MockProvider().complete("Q: k", sv).retrieval
    assert first == second
    assert [i.doc_id for i in first] == ["d2", "d1"]  # order preserved verbatim
    assert first[0].rank == 1 and first[0].score == 0.4
    assert first[1].rank == 0 and first[1].score is None


def test_retrieval_default_and_rank_fallback() -> None:
    sv = _sv(
        {
            "responses": {},
            "retrieval": {"Q: k": [{"doc_id": "hit", "content": "c"}]},
            "retrieval_default": [{"doc_id": "fallback", "content": "c"}],
        }
    )
    assert [i.doc_id for i in MockProvider().complete("Q: k", sv).retrieval] == ["hit"]
    other = MockProvider().complete("Q: other", sv).retrieval
    assert [i.doc_id for i in other] == ["fallback"]
    assert other[0].rank == 0  # rank defaults to position


@pytest.mark.parametrize(
    "mock",
    [
        {"retrieval": "not a map"},
        {"retrieval": {"p": "not a list"}},
        {"retrieval": {"p": [{"content": "no doc id"}]}},
        {"retrieval": {"p": [{"doc_id": "d", "rank": -1}]}},
        {"retrieval": {"p": [{"doc_id": "d", "score": "high"}]}},
        {"retrieval": {"p": [{"doc_id": "d", "unknown": 1}]}},
        {"retrieval_default": [{"doc_id": ""}]},
    ],
)
def test_malformed_retrieval_config_raises_config_error(mock: Any) -> None:
    with pytest.raises(ConfigError):
        MockProvider().complete("p", _sv(mock))


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
