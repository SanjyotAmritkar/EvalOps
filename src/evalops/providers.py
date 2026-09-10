"""Deterministic, offline provider implementations.

Phase 1 ships only :class:`MockProvider`, the permanent test/CI/offline-dev
double. It implements the domain ``ProviderClient`` protocol and is driven
entirely by ``config.parameters["mock"]`` on the ``SystemVersion`` passed to
:meth:`MockProvider.complete`.

The returned ``UsageMetrics`` are **synthetic test values**, not real tokenizer
or provider measurements: token counts are whitespace-word counts of the prompt
and response, latency is a configured constant, and cost is always ``0.0``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evalops.domain.contracts import ProviderError, ProviderResponse
from evalops.domain.entities import SystemVersion
from evalops.domain.value_objects import RetrievedItem, UsageMetrics
from evalops.errors import ConfigError

_MOCK_KEYS = frozenset(
    {"responses", "default", "latency_ms", "fail_on", "retrieval", "retrieval_default"}
)


def _parse_retrieval(raw: Any, where: str) -> tuple[RetrievedItem, ...]:
    """Parse a list of retrieved-item dicts into ``RetrievedItem`` objects.

    Each entry: ``{"doc_id": str, "content": str, "rank"?: int, "score"?: number}``.
    ``rank`` defaults to the entry's position. Order is preserved verbatim.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ConfigError(f"{where} must be a list of retrieved-item objects")
    items: list[RetrievedItem] = []
    for position, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ConfigError(f"{where}[{position}] must be an object")
        unknown = sorted(k for k in entry if k not in {"doc_id", "content", "rank", "score"})
        if unknown:
            raise ConfigError(f"{where}[{position}] has unknown key(s) {unknown}")
        doc_id = entry.get("doc_id")
        content = entry.get("content", "")
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ConfigError(f"{where}[{position}].doc_id must be a non-empty string")
        if not isinstance(content, str):
            raise ConfigError(f"{where}[{position}].content must be a string")
        rank = entry.get("rank", position)
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
            raise ConfigError(f"{where}[{position}].rank must be an integer >= 0")
        score = entry.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
            raise ConfigError(f"{where}[{position}].score must be a number")
        items.append(
            RetrievedItem(
                doc_id=doc_id,
                content=content,
                rank=rank,
                score=None if score is None else float(score),
            )
        )
    return tuple(items)


@dataclass(frozen=True, slots=True)
class _MockSpec:
    """Parsed, validated ``config.parameters["mock"]`` block."""

    responses: Mapping[str, str]
    default: str
    latency_ms: float
    fail_on: frozenset[str]
    retrieval: Mapping[str, tuple[RetrievedItem, ...]]
    retrieval_default: tuple[RetrievedItem, ...]

    @classmethod
    def from_config(cls, config: SystemVersion) -> _MockSpec:
        raw = config.parameters.get("mock", {})
        if not isinstance(raw, Mapping):
            raise ConfigError("parameters['mock'] must be a mapping")

        unknown = sorted(k for k in raw if k not in _MOCK_KEYS)
        if unknown:
            raise ConfigError(
                f"unknown key(s) {unknown} in parameters['mock']; allowed: {sorted(_MOCK_KEYS)}"
            )

        responses = raw.get("responses", {})
        if not isinstance(responses, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in responses.items()
        ):
            raise ConfigError(
                "parameters['mock']['responses'] must map prompt strings to response strings"
            )

        default = raw.get("default", "")
        if not isinstance(default, str):
            raise ConfigError("parameters['mock']['default'] must be a string")

        latency_ms = raw.get("latency_ms", 0.0)
        if (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, (int, float))
            or latency_ms < 0
        ):
            raise ConfigError("parameters['mock']['latency_ms'] must be a number >= 0")

        fail_on = raw.get("fail_on", [])
        if not isinstance(fail_on, (list, tuple)) or not all(isinstance(x, str) for x in fail_on):
            raise ConfigError("parameters['mock']['fail_on'] must be a list of strings")

        retrieval_raw = raw.get("retrieval", {})
        if not isinstance(retrieval_raw, Mapping) or not all(
            isinstance(k, str) for k in retrieval_raw
        ):
            raise ConfigError(
                "parameters['mock']['retrieval'] must map prompt strings to retrieved-item lists"
            )
        retrieval = {
            prompt: _parse_retrieval(items, f"parameters['mock']['retrieval'][{prompt!r}]")
            for prompt, items in retrieval_raw.items()
        }
        retrieval_default = _parse_retrieval(
            raw.get("retrieval_default", []), "parameters['mock']['retrieval_default']"
        )

        return cls(
            responses=dict(responses),
            default=default,
            latency_ms=float(latency_ms),
            fail_on=frozenset(fail_on),
            retrieval=retrieval,
            retrieval_default=retrieval_default,
        )


class MockProvider:
    """Deterministic offline ``ProviderClient``.

    No network, no randomness, no wall-clock measurement, no hidden state.
    ``complete`` is a pure function of the rendered ``prompt`` and the
    ``SystemVersion`` config: it looks the prompt up **exactly** in
    ``parameters['mock']['responses']`` (falling back to ``default``), and
    raises :class:`~evalops.domain.contracts.ProviderError` when the prompt is
    listed in ``fail_on``.
    """

    name = "mock"

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        spec = _MockSpec.from_config(config)
        if prompt in spec.fail_on:
            raise ProviderError("mock provider is configured to fail for this prompt")
        text = spec.responses.get(prompt, spec.default)
        usage = UsageMetrics(
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            cost_usd=0.0,
            latency_ms=spec.latency_ms,
        )
        retrieval = spec.retrieval.get(prompt, spec.retrieval_default)
        return ProviderResponse(text=text, usage=usage, retrieval=retrieval)
