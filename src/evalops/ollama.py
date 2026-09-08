"""Real local-provider adapter for Ollama.

Talks to a local Ollama server via ``POST /api/generate`` (non-streaming) using
only the standard library. Usage metrics come straight from Ollama's response --
nothing is fabricated. Expected provider/network failures are raised as
``ProviderError``; the runner turns those into failed ``EvaluationRun`` records.
"""

from __future__ import annotations

import json
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

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT_SECONDS = 120.0

_FLOAT_OPTIONS = frozenset({"temperature", "top_p"})
_INT_OPTIONS = frozenset({"seed", "num_predict"})
_ALLOWED_OPTIONS = _FLOAT_OPTIONS | _INT_OPTIONS
_MAX_ERROR_CHARS = 300
_NS_PER_MS = 1_000_000


def build_options(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Translate the allowlisted ``SystemVersion.parameters`` into Ollama options.

    The mock-only ``"mock"`` block is ignored. Any other key outside the small
    allowlist, or a value of the wrong type/range, raises :class:`ConfigError`.
    """
    options: dict[str, Any] = {}
    for key, value in parameters.items():
        if key == "mock":
            continue
        if key not in _ALLOWED_OPTIONS:
            raise ConfigError(
                f"parameters.{key!r} is not a supported Ollama generation parameter; "
                f"supported: {sorted(_ALLOWED_OPTIONS)} (plus 'mock' for the mock backend)"
            )
        if key in _FLOAT_OPTIONS:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ConfigError(f"parameters.{key} must be a number >= 0")
            options[key] = float(value)
        else:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConfigError(f"parameters.{key} must be an integer >= 0")
            options[key] = value
    return options


@dataclass(frozen=True, slots=True)
class OllamaProvider:
    """``ProviderClient`` backed by a local Ollama HTTP server.

    ``latency_ms`` on the returned usage is Ollama's server-reported
    ``total_duration`` for the whole request (model load + prompt eval +
    generation), converted from nanoseconds to milliseconds. It is not a
    client-measured round trip, and the first call for a model includes load
    time.
    """

    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    name: ClassVar[str] = "ollama"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        if config.provider is not ProviderName.OLLAMA:
            raise ProviderError(
                "OllamaProvider requires a SystemVersion with provider 'ollama', got "
                f"{config.provider.value!r}"
            )
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt, "stream": False}
        options = build_options(config.parameters)
        if options:
            payload["options"] = options

        body = self._post("/api/generate", payload)
        return _parse_generate_response(body, model=config.model)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            suffix = f" ({detail})" if detail else ""
            raise ProviderError(f"Ollama request to {url} failed: HTTP {exc.code}{suffix}") from exc
        except TimeoutError as exc:
            raise ProviderError(
                f"Ollama request to {url} timed out after {self.timeout_seconds:g}s"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Ollama request to {url} failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Ollama returned a non-JSON response from {url}") from exc
        if not isinstance(parsed, dict):
            raise ProviderError(f"Ollama returned an unexpected response shape from {url}")
        if "error" in parsed:
            raise ProviderError(f"Ollama error: {_truncate(str(parsed['error']))}")
        return parsed


def _parse_generate_response(body: dict[str, Any], *, model: str) -> ProviderResponse:
    text = body.get("response")
    if not isinstance(text, str):
        raise ProviderError(f"Ollama response for model {model!r} is missing 'response' text")

    total_duration = body.get("total_duration")
    if (
        isinstance(total_duration, bool)
        or not isinstance(total_duration, (int, float))
        or total_duration < 0
    ):
        raise ProviderError(
            f"Ollama response for model {model!r} has missing or invalid 'total_duration'"
        )

    return ProviderResponse(
        text=text,
        usage=UsageMetrics(
            prompt_tokens=_require_count(body, "prompt_eval_count", model),
            completion_tokens=_require_count(body, "eval_count", model),
            cost_usd=0.0,
            latency_ms=total_duration / _NS_PER_MS,
        ),
    )


def _require_count(body: dict[str, Any], key: str, model: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError(f"Ollama response for model {model!r} has missing or invalid {key!r}")
    return value


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return _truncate(exc.read().decode("utf-8", "replace"))
    except Exception:  # best-effort diagnostic only
        return ""


def _truncate(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_ERROR_CHARS else text[:_MAX_ERROR_CHARS] + "..."
