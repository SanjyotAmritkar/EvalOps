"""Resolve a :class:`ProviderName` to its real ``ProviderClient`` adapter.

One place that knows the mapping ``ollama -> OllamaProvider``,
``openai -> OpenAIProvider``, ``anthropic -> AnthropicProvider`` -- shared by
cross-provider execution (:func:`evalops.execution.build_providers`) and the LLM
judge evaluator. The deterministic ``MockProvider`` is not a real adapter and is
not resolvable here (there is no ``ProviderName.mock``).
"""

from __future__ import annotations

from evalops.cloud_providers import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
    AnthropicProvider,
    OpenAIProvider,
    require_api_key,
)
from evalops.domain.contracts import ProviderClient
from evalops.domain.enums import ProviderName
from evalops.errors import ConfigError
from evalops.ollama import DEFAULT_BASE_URL as DEFAULT_OLLAMA_BASE_URL
from evalops.ollama import DEFAULT_TIMEOUT_SECONDS, OllamaProvider

_DEFAULT_BASE_URL = {
    ProviderName.OLLAMA: DEFAULT_OLLAMA_BASE_URL,
    ProviderName.OPENAI: DEFAULT_OPENAI_BASE_URL,
    ProviderName.ANTHROPIC: DEFAULT_ANTHROPIC_BASE_URL,
}


def make_provider(
    name: ProviderName,
    *,
    base_url: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    require_credentials: bool = True,
) -> ProviderClient:
    """Build the real adapter for ``name``.

    ``base_url`` falls back to each provider's public default. When
    ``require_credentials`` is set (the default), a missing API-key env var
    raises :class:`ConfigError` here rather than mid-run.
    """
    if timeout_seconds <= 0:
        raise ConfigError("provider timeout_seconds must be greater than 0")
    resolved = base_url or _DEFAULT_BASE_URL.get(name)
    if resolved is None:
        raise ConfigError(f"no real provider adapter for {name.value!r}")

    if require_credentials:
        require_api_key(name)

    if name is ProviderName.OLLAMA:
        return OllamaProvider(base_url=resolved, timeout_seconds=timeout_seconds)
    if name is ProviderName.OPENAI:
        return OpenAIProvider(base_url=resolved, timeout_seconds=timeout_seconds)
    if name is ProviderName.ANTHROPIC:
        return AnthropicProvider(base_url=resolved, timeout_seconds=timeout_seconds)
    raise ConfigError(f"no real provider adapter for {name.value!r}")  # pragma: no cover
