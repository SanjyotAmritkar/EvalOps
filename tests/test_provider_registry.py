"""Cross-provider execution: build_providers + make_provider.

Proves a baseline and candidate on *different* providers/models need no change
to the Experiment/SystemVersion shape -- only a two-entry provider map. No
network; hosted keys are throwaway strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from evalops.cloud_providers import AnthropicProvider, OpenAIProvider
from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.execution import ExecutionSpec, build_providers
from evalops.ollama import OllamaProvider
from evalops.provider_registry import make_provider
from evalops.providers import MockProvider


def _sv(
    provider: ProviderName, *, model: str = "m", parameters: Mapping[str, Any] | None = None
) -> SystemVersion:
    return SystemVersion(
        project_id="p",
        name="cfg",
        version="v1",
        provider=provider,
        model=model,
        prompt_template="Q: ${input}",
        parameters=parameters or {},
    )


@pytest.fixture
def _fake_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


# --- make_provider --------------------------------------------------


def test_make_provider_resolves_each_name(_fake_keys: None) -> None:
    assert isinstance(make_provider(ProviderName.OLLAMA), OllamaProvider)
    assert isinstance(make_provider(ProviderName.OPENAI), OpenAIProvider)
    assert isinstance(make_provider(ProviderName.ANTHROPIC), AnthropicProvider)


def test_make_provider_checks_credentials_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        make_provider(ProviderName.OPENAI)
    # opt out for construction-only use
    assert isinstance(make_provider(ProviderName.OPENAI, require_credentials=False), OpenAIProvider)


def test_make_provider_threads_base_url_and_timeout(_fake_keys: None) -> None:
    provider = make_provider(
        ProviderName.OPENAI, base_url="http://localhost:9099/v1", timeout_seconds=7
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "http://localhost:9099/v1"
    assert provider.timeout_seconds == 7.0


# --- build_providers: mock / ollama unchanged ----------------------


def test_mock_backend_is_unchanged() -> None:
    providers = build_providers(
        ExecutionSpec(backend="mock"), _sv(ProviderName.OPENAI), _sv(ProviderName.ANTHROPIC)
    )
    assert set(providers) == {ProviderName.OPENAI, ProviderName.ANTHROPIC}
    assert all(isinstance(p, MockProvider) for p in providers.values())


def test_ollama_backend_is_unchanged() -> None:
    providers = build_providers(
        ExecutionSpec(backend="ollama", base_url="http://ollama.local:1234/"),
        _sv(ProviderName.OLLAMA),
        _sv(ProviderName.OLLAMA),
    )
    assert set(providers) == {ProviderName.OLLAMA}
    provider = providers[ProviderName.OLLAMA]
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://ollama.local:1234"


def test_ollama_backend_still_rejects_a_non_ollama_version() -> None:
    with pytest.raises(ConfigError, match="must be 'ollama'"):
        build_providers(
            ExecutionSpec(backend="ollama"),
            _sv(ProviderName.OLLAMA),
            _sv(ProviderName.OPENAI),
        )


# --- build_providers: hosted single-provider modes ---------------


def test_openai_backend_requires_both_versions_to_be_openai(_fake_keys: None) -> None:
    providers = build_providers(
        ExecutionSpec(backend="openai"),
        _sv(ProviderName.OPENAI, model="gpt-4o-mini"),
        _sv(ProviderName.OPENAI, model="gpt-4o"),
    )
    assert set(providers) == {ProviderName.OPENAI}
    assert isinstance(providers[ProviderName.OPENAI], OpenAIProvider)


def test_openai_backend_rejects_an_anthropic_version(_fake_keys: None) -> None:
    with pytest.raises(ConfigError, match="it must be 'openai'"):
        build_providers(
            ExecutionSpec(backend="openai"),
            _sv(ProviderName.OPENAI),
            _sv(ProviderName.ANTHROPIC),
        )


def test_hosted_backend_fails_fast_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        build_providers(
            ExecutionSpec(backend="anthropic"),
            _sv(ProviderName.ANTHROPIC),
            _sv(ProviderName.ANTHROPIC),
        )


# --- build_providers: live / cross-provider ----------------------


def test_live_backend_honours_each_versions_own_provider(_fake_keys: None) -> None:
    # Ollama baseline vs OpenAI candidate
    providers = build_providers(
        ExecutionSpec(backend="live"),
        _sv(ProviderName.OLLAMA, model="llama3.2"),
        _sv(ProviderName.OPENAI, model="gpt-4o-mini"),
    )
    assert set(providers) == {ProviderName.OLLAMA, ProviderName.OPENAI}
    assert isinstance(providers[ProviderName.OLLAMA], OllamaProvider)
    assert isinstance(providers[ProviderName.OPENAI], OpenAIProvider)


def test_live_backend_openai_vs_anthropic(_fake_keys: None) -> None:
    providers = build_providers(
        ExecutionSpec(backend="live"),
        _sv(ProviderName.OPENAI, model="gpt-4o"),
        _sv(ProviderName.ANTHROPIC, model="claude-3-5-sonnet"),
    )
    assert set(providers) == {ProviderName.OPENAI, ProviderName.ANTHROPIC}


def test_live_backend_same_provider_different_models_is_one_entry(_fake_keys: None) -> None:
    providers = build_providers(
        ExecutionSpec(backend="live"),
        _sv(ProviderName.OPENAI, model="gpt-4o-mini"),
        _sv(ProviderName.OPENAI, model="gpt-4o"),
    )
    assert set(providers) == {ProviderName.OPENAI}


def test_live_backend_validates_generation_params_per_provider(_fake_keys: None) -> None:
    with pytest.raises(ConfigError, match="not a supported OpenAI generation parameter"):
        build_providers(
            ExecutionSpec(backend="live"),
            _sv(ProviderName.OLLAMA),
            _sv(ProviderName.OPENAI, parameters={"frequency_penalty": 0.2}),
        )
