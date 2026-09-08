"""Provider and evaluator contracts.

Synchronous protocols for V1: no async, no retry, no batching. Implementations
live in later phases (``gateway`` for providers, ``eval`` for evaluators).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from evalops.domain.entities import DatasetCase, EvaluationRun, SystemVersion
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.errors import EvalOpsError
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics


class ProviderError(EvalOpsError):
    """Raised by a ProviderClient when a completion cannot be produced."""


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """The result of a single provider completion call."""

    text: str
    usage: UsageMetrics


@runtime_checkable
class ProviderClient(Protocol):
    """A synchronous client for one model provider."""

    name: str

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        """Return a completion for an already fully rendered ``prompt``.

        ``config`` supplies the provider, model, and parameters. Raise
        ``ProviderError`` when a completion cannot be produced.
        """
        ...


@runtime_checkable
class Evaluator(Protocol):
    """A synchronous scorer for one evaluation dimension."""

    name: str
    family: EvaluatorFamily

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        """Score a single EvaluationRun against its reference DatasetCase."""
        ...
