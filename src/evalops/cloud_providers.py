"""Hosted-provider adapters for OpenAI and Anthropic.

These reuse the repository's established, dependency-free HTTP pattern (see
:class:`evalops.ollama.OllamaProvider` and ``tests/test_ollama_provider.py``):
a plain ``urllib`` ``POST`` of JSON, with every provider/network/API failure
mapped to :class:`~evalops.domain.contracts.ProviderError`. No SDKs, no retries,
no streaming.

**Secrets:** API keys are read from the environment only
(``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``) at call time. They are never stored
on the provider object, logged, placed in config, or serialised into a task.

**Usage / cost:** token counts come straight from the provider response; a
missing count is recorded as ``0``, never guessed. ``cost_usd`` is always
``0.0`` -- EvalOps does not ship a pricing table and will not fabricate one.
``latency_ms`` is a client-measured round trip (includes network), since these
APIs do not return a trustworthy server-side duration.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from evalops.domain.contracts import ProviderError, ProviderResponse
from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.domain.value_objects import UsageMetrics
from evalops.errors import ConfigError

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_TIMEOUT_SECONDS = 120.0
ANTHROPIC_VERSION = "2023-06-01"
#: Anthropic requires an explicit ``max_tokens``; used when the config sets none.
DEFAULT_ANTHROPIC_MAX_TOKENS = 1024

_FLOAT_PARAMS = frozenset({"temperature", "top_p"})
_INT_PARAMS = frozenset({"max_tokens"})
_ALLOWED_PARAMS = _FLOAT_PARAMS | _INT_PARAMS
_MAX_ERROR_CHARS = 300
_ENV_VAR = {ProviderName.OPENAI: "OPENAI_API_KEY", ProviderName.ANTHROPIC: "ANTHROPIC_API_KEY"}


def cloud_params(parameters: Mapping[str, Any], *, provider: str) -> dict[str, Any]:
    """Translate the allowlisted ``SystemVersion.parameters`` for a hosted call.

    Allowed: ``temperature`` / ``top_p`` (number >= 0) and ``max_tokens``
    (integer >= 1). The mock-only ``"mock"`` block is ignored. Anything else
    raises :class:`ConfigError` -- the same fail-fast contract as
    :func:`evalops.ollama.build_options`.
    """
    out: dict[str, Any] = {}
    for key, value in parameters.items():
        if key == "mock":
            continue
        if key not in _ALLOWED_PARAMS:
            raise ConfigError(
                f"parameters.{key!r} is not a supported {provider} generation parameter; "
                f"supported: {sorted(_ALLOWED_PARAMS)} (plus 'mock' for the mock backend)"
            )
        if key in _FLOAT_PARAMS:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ConfigError(f"parameters.{key} must be a number >= 0")
            out[key] = float(value)
        else:  # max_tokens
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ConfigError(f"parameters.{key} must be an integer >= 1")
            out[key] = value
    return out


def _api_key(provider: ProviderName) -> str:
    env_var = _ENV_VAR[provider]
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise ConfigError(
            f"the {provider.value} provider requires the {env_var} environment variable, "
            f"which is not set. API keys are read from the environment only -- never from "
            f"a config file, the database, or a request body."
        )
    return key


def require_api_key(provider: ProviderName) -> None:
    """Raise :class:`ConfigError` unless the provider's key env var is set.

    Called at plan-build time so a missing key fails fast, before any case runs.
    Ollama and the mock backend have no key and are a no-op here.
    """
    if provider in _ENV_VAR:
        _api_key(provider)


def _truncate(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + "..."


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return _truncate(exc.read().decode("utf-8", "replace"))
    except Exception:  # best-effort diagnostic only
        return ""


def _post_json(
    url: str, *, headers: Mapping[str, str], payload: Mapping[str, Any], timeout: float, label: str
) -> dict[str, Any]:
    """``POST`` ``payload`` as JSON and return the parsed object.

    Mirrors :meth:`evalops.ollama.OllamaProvider._post`: HTTP, timeout, and
    transport errors all become :class:`ProviderError`.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _read_error_body(exc)
        suffix = f" ({detail})" if detail else ""
        raise ProviderError(f"{label} request to {url} failed: HTTP {exc.code}{suffix}") from exc
    except TimeoutError as exc:
        raise ProviderError(f"{label} request to {url} timed out after {timeout:g}s") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"{label} request to {url} failed: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{label} returned a non-JSON response from {url}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError(f"{label} returned an unexpected response shape from {url}")
    return parsed


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _usage_map(body: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = body.get("usage")
    return raw if isinstance(raw, Mapping) else {}


@dataclass(frozen=True, slots=True)
class OpenAIProvider:
    """``ProviderClient`` for the OpenAI Chat Completions API.

    ``base_url`` defaults to the public API; override it (e.g. for an
    OpenAI-compatible gateway) via config or the ``OPENAI_BASE_URL`` env var.
    """

    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    name: ClassVar[str] = "openai"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        if config.provider is not ProviderName.OPENAI:
            raise ProviderError(
                "OpenAIProvider requires a SystemVersion with provider 'openai', got "
                f"{config.provider.value!r}"
            )
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            **cloud_params(config.parameters, provider="OpenAI"),
        }
        headers = {"Authorization": f"Bearer {_api_key(ProviderName.OPENAI)}"}
        started = time.perf_counter()
        body = _post_json(
            f"{self.base_url}/chat/completions",
            headers=headers,
            payload=payload,
            timeout=self.timeout_seconds,
            label="OpenAI",
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _parse_openai(body, model=config.model, latency_ms=latency_ms)


def _parse_openai(body: dict[str, Any], *, model: str, latency_ms: float) -> ProviderResponse:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError(f"OpenAI response for model {model!r} has no choices")
    message = choices[0].get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str):
        raise ProviderError(
            f"OpenAI response for model {model!r} is missing choices[0].message.content"
        )
    usage = _usage_map(body)
    return ProviderResponse(
        text=text,
        usage=UsageMetrics(
            prompt_tokens=_int_or_zero(usage.get("prompt_tokens")),
            completion_tokens=_int_or_zero(usage.get("completion_tokens")),
            cost_usd=0.0,
            latency_ms=latency_ms,
        ),
    )


@dataclass(frozen=True, slots=True)
class AnthropicProvider:
    """``ProviderClient`` for the Anthropic Messages API.

    ``max_tokens`` is required by the API; when the config sets none,
    :data:`DEFAULT_ANTHROPIC_MAX_TOKENS` is used.
    """

    base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    name: ClassVar[str] = "anthropic"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        if config.provider is not ProviderName.ANTHROPIC:
            raise ProviderError(
                "AnthropicProvider requires a SystemVersion with provider 'anthropic', got "
                f"{config.provider.value!r}"
            )
        params = cloud_params(config.parameters, provider="Anthropic")
        params.setdefault("max_tokens", DEFAULT_ANTHROPIC_MAX_TOKENS)
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            **params,
        }
        headers = {
            "x-api-key": _api_key(ProviderName.ANTHROPIC),
            "anthropic-version": ANTHROPIC_VERSION,
        }
        started = time.perf_counter()
        body = _post_json(
            f"{self.base_url}/messages",
            headers=headers,
            payload=payload,
            timeout=self.timeout_seconds,
            label="Anthropic",
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _parse_anthropic(body, model=config.model, latency_ms=latency_ms)


def _parse_anthropic(body: dict[str, Any], *, model: str, latency_ms: float) -> ProviderResponse:
    blocks = body.get("content")
    if not isinstance(blocks, list):
        raise ProviderError(f"Anthropic response for model {model!r} has no content")
    parts = [
        block["text"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    if not parts:
        raise ProviderError(
            f"Anthropic response for model {model!r} contains no text content block"
        )
    usage = _usage_map(body)
    return ProviderResponse(
        text="".join(parts),
        usage=UsageMetrics(
            prompt_tokens=_int_or_zero(usage.get("input_tokens")),
            completion_tokens=_int_or_zero(usage.get("output_tokens")),
            cost_usd=0.0,
            latency_ms=latency_ms,
        ),
    )
