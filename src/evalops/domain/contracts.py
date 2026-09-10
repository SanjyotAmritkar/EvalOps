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
from evalops.domain.value_objects import (
    EvaluatorScore,
    RetrievedItem,
    ToolCall,
    UsageMetrics,
)


class ProviderError(EvalOpsError):
    """Raised by a ProviderClient when a completion cannot be produced."""


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """The result of a single provider completion call.

    ``retrieval`` (Phase 9) lets a RAG-capable provider report the context it
    retrieved; ``tool_calls`` (CP 9.2) lets an agent provider report its
    tool-call trajectory. Both default to empty, so every existing text-only
    provider keeps returning ``ProviderResponse(text=..., usage=...)`` unchanged.
    EvalOps does not perform retrieval or execute tools -- these only record what
    the external system reports.
    """

    text: str
    usage: UsageMetrics
    retrieval: tuple[RetrievedItem, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "retrieval", tuple(self.retrieval))
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))


@runtime_checkable
class ProviderClient(Protocol):
    """A synchronous client for one model provider.

    ``name`` is read-only descriptive metadata; an implementation may back it
    with a plain attribute, a class attribute, a frozen field, or a property.
    """

    @property
    def name(self) -> str: ...

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        """Return a completion for an already fully rendered ``prompt``.

        ``config`` supplies the provider, model, and parameters. Raise
        ``ProviderError`` when a completion cannot be produced.
        """
        ...


@runtime_checkable
class Evaluator(Protocol):
    """A synchronous scorer for one evaluation dimension.

    ``name`` and ``family`` are read-only descriptive metadata; an
    implementation may back them with plain attributes, class attributes,
    frozen fields, or properties.
    """

    @property
    def name(self) -> str: ...

    @property
    def family(self) -> EvaluatorFamily: ...

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        """Score a single EvaluationRun against its reference DatasetCase."""
        ...
