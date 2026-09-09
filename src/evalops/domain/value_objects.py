"""Immutable value objects used by domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """Baseline-vs-candidate values for one named metric within an experiment.

    Representation only: it holds the two values and exposes their difference.
    Statistical comparison (confidence intervals, significance) and any
    pass/fail verdict are added by later phases, not here.
    """

    metric: str
    baseline_value: float
    candidate_value: float

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise DomainValidationError("metric must be a non-empty string")

    @property
    def delta(self) -> float:
        """Candidate value minus baseline value."""
        return self.candidate_value - self.baseline_value

    @property
    def relative_delta(self) -> float | None:
        """``delta`` as a fraction of the baseline, or ``None`` if baseline is 0."""
        if self.baseline_value == 0:
            return None
        return self.delta / self.baseline_value


# --- statistical evidence (Phase 5) --------------------------------------

#: Whether a metric's per-run observations are 0/1 indicators or real-valued.
MetricKind = Literal["binary", "continuous"]


@dataclass(frozen=True, slots=True)
class SampleSummary:
    """Descriptive statistics for one series of per-pair observations.

    Representation only. Computed by :mod:`evalops.stats`; stored on
    :class:`MetricEvidence` and round-tripped through persistence.
    """

    n: int
    mean: float
    median: float
    stdev: float  # sample standard deviation (ddof=1); 0.0 when n < 2

    def __post_init__(self) -> None:
        if self.n < 0:
            raise DomainValidationError(f"SampleSummary.n must be >= 0, got {self.n}")
        if self.stdev < 0.0:
            raise DomainValidationError(f"SampleSummary.stdev must be >= 0, got {self.stdev!r}")


@dataclass(frozen=True, slots=True)
class MetricEvidence:
    """Statistical evidence for one metric's baseline->candidate change.

    A paired-bootstrap view (see :mod:`evalops.stats`) of one metric, suitable
    for release gating and API output. ``ci_excludes_zero`` is a mechanical
    property of the interval and is only meaningful when
    ``insufficient_evidence`` is ``False``. ``baseline``, ``candidate`` and
    ``paired_delta`` all summarise ``n_pairs`` observations.
    """

    metric: str
    kind: MetricKind
    n_pairs: int
    baseline: SampleSummary
    candidate: SampleSummary
    paired_delta: SampleSummary  # summary of (candidate_i - baseline_i)
    delta: float  # candidate.mean - baseline.mean (== paired_delta.mean)
    relative_change: float | None  # delta / baseline.mean; None if baseline.mean == 0
    confidence_level: float
    ci_low: float | None
    ci_high: float | None
    ci_excludes_zero: bool
    insufficient_evidence: bool
    method: str
    resamples: int
    seed: int
    dropped_provider_failures: int = 0

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise DomainValidationError("MetricEvidence.metric must be a non-empty string")
        if self.kind not in ("binary", "continuous"):
            raise DomainValidationError(f"MetricEvidence.kind is invalid: {self.kind!r}")
        if self.n_pairs < 0:
            raise DomainValidationError(f"MetricEvidence.n_pairs must be >= 0, got {self.n_pairs}")
        if not 0.0 < self.confidence_level < 1.0:
            raise DomainValidationError(
                f"MetricEvidence.confidence_level must be in (0, 1), got {self.confidence_level!r}"
            )
        if (self.ci_low is None) != (self.ci_high is None):
            raise DomainValidationError(
                "MetricEvidence.ci_low and ci_high must both be set or both be None"
            )
        if self.ci_low is not None and self.ci_high is not None and self.ci_low > self.ci_high:
            raise DomainValidationError(
                f"MetricEvidence CI is inverted: [{self.ci_low}, {self.ci_high}]"
            )
        if self.dropped_provider_failures < 0:
            raise DomainValidationError(
                "MetricEvidence.dropped_provider_failures must be >= 0, "
                f"got {self.dropped_provider_failures}"
            )
        for label, summary in (
            ("baseline", self.baseline),
            ("candidate", self.candidate),
            ("paired_delta", self.paired_delta),
        ):
            if summary.n != self.n_pairs:
                raise DomainValidationError(
                    f"MetricEvidence.{label}.n ({summary.n}) != n_pairs ({self.n_pairs})"
                )
