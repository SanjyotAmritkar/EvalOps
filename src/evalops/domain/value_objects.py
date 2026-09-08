"""Immutable value objects used by domain entities."""

from __future__ import annotations

from dataclasses import dataclass

from evalops.domain.enums import EvaluatorFamily
from evalops.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class UsageMetrics:
    """Token, cost, and latency accounting for a single model call.

    Recorded on every EvaluationRun so an experiment's cost and latency can be
    compared between baseline and candidate. A failed run carries the zero value.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("prompt_tokens", self.prompt_tokens),
            ("completion_tokens", self.completion_tokens),
            ("cost_usd", self.cost_usd),
            ("latency_ms", self.latency_ms),
        ):
            if value < 0:
                raise DomainValidationError(f"{name} must be non-negative, got {value!r}")

    @property
    def total_tokens(self) -> int:
        """Prompt tokens plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class EvaluatorScore:
    """The result a single Evaluator produces for a single EvaluationRun.

    Multiple EvaluatorScores compose into a CaseResult; experiment-level
    aggregation of CaseResults eventually produces an EvaluationResult.
    """

    evaluator: str
    family: EvaluatorFamily
    score: float
    passed: bool | None = None

    def __post_init__(self) -> None:
        if not self.evaluator.strip():
            raise DomainValidationError("evaluator must be a non-empty string")
        if not 0.0 <= self.score <= 1.0:
            raise DomainValidationError(f"score must be within [0.0, 1.0], got {self.score!r}")
