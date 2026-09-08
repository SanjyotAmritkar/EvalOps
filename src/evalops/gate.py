"""Release-policy gating for an EvaluationResult.

Turns per-metric baseline-vs-candidate comparisons plus a ReleasePolicy into a
PASS/BLOCK decision. Representation only lives here -- no decision is stored on
the EvaluationResult. Phase 1 uses a closed metric-direction mapping; no
generic metric registry, no statistical gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from evalops.domain.entities import EvaluationResult, ReleasePolicy
from evalops.domain.enums import ReleaseDecision
from evalops.domain.value_objects import MetricComparison
from evalops.errors import ConfigError

Direction = Literal["higher_is_better", "lower_is_better"]

_LOWER_IS_BETTER = frozenset({"latency_ms.mean", "latency_ms.p95", "cost_usd.total"})


@dataclass(frozen=True, slots=True)
class MetricVerdict:
    """One metric's baseline-vs-candidate outcome under the policy."""

    metric: str
    direction: Direction
    baseline: float
    candidate: float
    adverse_change: float | None  # fraction; None => unbounded (zero baseline, adverse move)
    threshold: float | None  # None => this metric is not gated
    regression: bool


@dataclass(frozen=True, slots=True)
class GateReport:
    """Result of applying a ReleasePolicy to an EvaluationResult."""

    decision: ReleaseDecision  # PASS or BLOCK
    verdicts: tuple[MetricVerdict, ...]
    reasons: tuple[str, ...]
    gated: bool  # False when no ReleasePolicy was supplied


def evaluate_gate(result: EvaluationResult, policy: ReleasePolicy | None) -> GateReport:
    """Compare each metric against the policy and return a PASS/BLOCK report."""
    if policy is None:
        verdicts = tuple(_verdict(mc, threshold=None) for mc in result.metrics)
        return GateReport(decision=ReleaseDecision.PASS, verdicts=verdicts, reasons=(), gated=False)

    produced = {mc.metric for mc in result.metrics}
    unknown = sorted(m for m in policy.thresholds if m not in produced)
    if unknown:
        raise ConfigError(
            f"release policy references metric(s) not produced by the evaluation: {unknown}"
        )

    verdicts = tuple(
        _verdict(mc, threshold=policy.thresholds.get(mc.metric)) for mc in result.metrics
    )
    reasons = tuple(_reason(v) for v in verdicts if v.regression)
    decision = ReleaseDecision.BLOCK if reasons else ReleaseDecision.PASS
    return GateReport(decision=decision, verdicts=verdicts, reasons=reasons, gated=True)


def _direction(metric: str) -> Direction:
    if metric in _LOWER_IS_BETTER:
        return "lower_is_better"
    if metric == "success_rate" or metric.endswith(".pass_rate"):
        return "higher_is_better"
    raise ConfigError(f"gate has no direction rule for metric {metric!r}")


def _verdict(mc: MetricComparison, *, threshold: float | None) -> MetricVerdict:
    direction = _direction(mc.metric)
    baseline, candidate = mc.baseline_value, mc.candidate_value

    if baseline == 0 and candidate == 0:
        adverse: float | None = 0.0
        regression = False
    elif baseline == 0:
        if direction == "higher_is_better":
            adverse, regression = 0.0, False
        else:  # lower-is-better with a non-zero candidate: unbounded increase
            adverse = None
            regression = threshold is not None
    elif direction == "higher_is_better":
        adverse = (baseline - candidate) / baseline
        regression = threshold is not None and adverse > threshold
    else:
        adverse = (candidate - baseline) / baseline
        regression = threshold is not None and adverse > threshold

    return MetricVerdict(
        metric=mc.metric,
        direction=direction,
        baseline=baseline,
        candidate=candidate,
        adverse_change=adverse,
        threshold=threshold,
        regression=regression,
    )


def _reason(verdict: MetricVerdict) -> str:
    assert verdict.threshold is not None  # a regression always has a threshold
    if verdict.adverse_change is None:
        return (
            f"{verdict.metric}: increased from a zero baseline to {verdict.candidate:g} "
            f"(unbounded regression; cannot be expressed as a finite percentage; "
            f"limit {verdict.threshold:.0%})"
        )
    return (
        f"{verdict.metric}: {verdict.direction.replace('_', '-')} regression of "
        f"{verdict.adverse_change:.1%} (limit {verdict.threshold:.0%})"
    )
