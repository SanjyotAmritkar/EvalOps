"""Release-policy gating for an EvaluationResult.

Turns per-metric baseline-vs-candidate comparisons plus a ReleasePolicy into a
PASS/BLOCK decision. Representation only lives here -- no decision is stored on
the EvaluationResult. A closed metric-direction mapping; no generic metric
registry.

Phase 5 (CP 5.2) adds a **statistical guard**: for metrics that carry paired
bootstrap ``MetricEvidence`` (``EvaluationResult.evidence``), a policy-threshold
breach only BLOCKS when the evidence actually supports an adverse regression
*beyond the tolerated boundary*. The policy threshold still defines the maximum
tolerated effect; statistics only stop weak/noisy breaches from blocking. See
``docs/ARCHITECTURE.md`` section 8.2 for the exact semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from evalops.domain.entities import EvaluationResult, ReleasePolicy
from evalops.domain.enums import ReleaseDecision
from evalops.domain.value_objects import MetricComparison, MetricEvidence
from evalops.errors import ConfigError

Direction = Literal["higher_is_better", "lower_is_better"]

#: Per-metric gate outcome.
#: * ``pass``                    -- adverse change within the tolerated threshold.
#: * ``regression``              -- BLOCKS: a deterministic metric breached its
#:                                  threshold, or a statistical metric breached
#:                                  *and* its CI confirms a regression beyond
#:                                  tolerance.
#: * ``regression_inconclusive`` -- breached, evidence available and sufficient,
#:                                  but the CI does not confirm it -> does NOT block.
#: * ``regression_low_evidence`` -- breached, but fewer than
#:                                  :data:`MIN_PAIRS_TO_BLOCK` comparable pairs ->
#:                                  does NOT block.
GateOutcome = Literal[
    "pass",
    "regression",
    "regression_inconclusive",
    "regression_low_evidence",
]

_LOWER_IS_BETTER = frozenset({"latency_ms.mean", "latency_ms.p95", "cost_usd.total"})

#: Minimum comparable pairs before a threshold breach may BLOCK on statistical
#: grounds. Below this, the breach is reported as an advisory only and the
#: deterministic metrics still gate normally. Fixed for this phase: a paired
#: percentile bootstrap needs enough distinct pairs that its tail quantiles
#: reflect a distribution rather than one or two runs, and 8 (e.g. 4 cases x 2
#: repeats, or 8 x 1) is a deliberately conservative floor. It is a constant
#: rather than a ReleasePolicy field because ``ReleasePolicy.thresholds`` is a
#: flat metric->float map -- a per-policy knob would need a domain field, a
#: column, and a migration, which exceeds "very little complexity". Teams gain
#: statistical power by raising ``repeats`` or dataset size.
MIN_PAIRS_TO_BLOCK = 8


@dataclass(frozen=True, slots=True)
class MetricVerdict:
    """One metric's baseline-vs-candidate outcome under the policy."""

    metric: str
    direction: Direction
    baseline: float
    candidate: float
    adverse_change: float | None  # fraction; None => unbounded (zero baseline, adverse move)
    threshold: float | None  # None => this metric is not gated
    regression: bool  # drives BLOCK; True iff outcome == "regression"
    # CP 5.2 -----------------------------------------------------------------
    outcome: GateOutcome
    threshold_breached: bool  # point adverse_change exceeded the threshold
    evidence: MetricEvidence | None  # the statistical evidence considered, if any


@dataclass(frozen=True, slots=True)
class GateReport:
    """Result of applying a ReleasePolicy to an EvaluationResult."""

    decision: ReleaseDecision  # PASS or BLOCK
    verdicts: tuple[MetricVerdict, ...]
    reasons: tuple[str, ...]  # blocking regressions only (unchanged meaning)
    advisories: tuple[str, ...]  # CP 5.2: threshold breaches that did NOT block
    gated: bool  # False when no ReleasePolicy was supplied


def evaluate_gate(result: EvaluationResult, policy: ReleasePolicy | None) -> GateReport:
    """Compare each metric against the policy and return a PASS/BLOCK report.

    Statistical evidence, when present on ``result.evidence`` for a metric, is
    read here -- there is no separate evidence argument, so every caller (sync
    run, worker, and the ``GET /results`` recompute) gates identically.
    """
    evidence_by_metric = {e.metric: e for e in result.evidence}

    if policy is None:
        verdicts = tuple(
            _verdict(mc, threshold=None, evidence=evidence_by_metric.get(mc.metric))
            for mc in result.metrics
        )
        return GateReport(
            decision=ReleaseDecision.PASS,
            verdicts=verdicts,
            reasons=(),
            advisories=(),
            gated=False,
        )

    produced = {mc.metric for mc in result.metrics}
    unknown = sorted(m for m in policy.thresholds if m not in produced)
    if unknown:
        raise ConfigError(
            f"release policy references metric(s) not produced by the evaluation: {unknown}"
        )

    verdicts = tuple(
        _verdict(
            mc,
            threshold=policy.thresholds.get(mc.metric),
            evidence=evidence_by_metric.get(mc.metric),
        )
        for mc in result.metrics
    )
    reasons = tuple(_reason(v) for v in verdicts if v.outcome == "regression")
    advisories = tuple(
        _advisory(v)
        for v in verdicts
        if v.outcome in ("regression_inconclusive", "regression_low_evidence")
    )
    decision = ReleaseDecision.BLOCK if reasons else ReleaseDecision.PASS
    return GateReport(
        decision=decision,
        verdicts=verdicts,
        reasons=reasons,
        advisories=advisories,
        gated=True,
    )


def _direction(metric: str) -> Direction:
    if metric in _LOWER_IS_BETTER:
        return "lower_is_better"
    if metric == "success_rate" or metric.endswith(".pass_rate") or metric.endswith(".mean_score"):
        # CP 9.2: a graded evaluator mean_score is always higher-is-better
        # (EvaluatorScore.score: 1.0 == best). No RAG/agent-specific rule.
        return "higher_is_better"
    raise ConfigError(f"gate has no direction rule for metric {metric!r}")


def _verdict(
    mc: MetricComparison,
    *,
    threshold: float | None,
    evidence: MetricEvidence | None,
) -> MetricVerdict:
    direction = _direction(mc.metric)
    baseline, candidate = mc.baseline_value, mc.candidate_value

    if baseline == 0 and candidate == 0:
        adverse: float | None = 0.0
        threshold_breached = False
    elif baseline == 0:
        if direction == "higher_is_better":
            adverse, threshold_breached = 0.0, False
        else:  # lower-is-better with a non-zero candidate: unbounded increase
            adverse = None
            threshold_breached = threshold is not None
    elif direction == "higher_is_better":
        adverse = (baseline - candidate) / baseline
        threshold_breached = threshold is not None and adverse > threshold
    else:
        adverse = (candidate - baseline) / baseline
        threshold_breached = threshold is not None and adverse > threshold

    outcome = _outcome(threshold_breached, threshold, direction, evidence)

    return MetricVerdict(
        metric=mc.metric,
        direction=direction,
        baseline=baseline,
        candidate=candidate,
        adverse_change=adverse,
        threshold=threshold,
        regression=outcome == "regression",
        outcome=outcome,
        threshold_breached=threshold_breached,
        evidence=evidence,
    )


def _outcome(
    threshold_breached: bool,
    threshold: float | None,
    direction: Direction,
    evidence: MetricEvidence | None,
) -> GateOutcome:
    """Combine the deterministic point breach with the statistical guard.

    * No breach                              -> ``pass``.
    * Breach, metric has no evidence          -> ``regression`` (deterministic;
      preserves pre-Phase-5 behaviour for ``latency_ms.p95`` / ``cost_usd.total``).
    * Breach, too few pairs / no CI           -> ``regression_low_evidence``.
    * Breach, CI confirms adverse regression
      beyond the tolerated boundary           -> ``regression``.
    * Breach, CI does not confirm it          -> ``regression_inconclusive``.
    """
    if not threshold_breached:
        return "pass"
    if evidence is None:
        return "regression"
    if evidence.n_pairs < MIN_PAIRS_TO_BLOCK or evidence.ci_low is None or evidence.ci_high is None:
        return "regression_low_evidence"
    if _ci_confirms_regression(evidence, direction, threshold):
        return "regression"
    return "regression_inconclusive"


def _ci_confirms_regression(
    evidence: MetricEvidence, direction: Direction, threshold: float | None
) -> bool:
    """Does the CI for ``delta = candidate.mean - baseline.mean`` lie entirely
    on the adverse side of the policy's tolerated-regression boundary?

    The boundary is expressed in the same units as the CI. With
    ``ref = evidence.baseline.mean`` and tolerated fraction ``t = threshold``:

    * higher_is_better -- adverse is a *decrease*; tolerated floor is
      ``ref * (1 - t)``, i.e. delta down to ``-t * ref``. The CI confirms a
      regression when its **upper** bound is still below that: ``ci_high < -t*ref``.
    * lower_is_better  -- adverse is an *increase*; tolerated ceiling is
      ``ref * (1 + t)``, i.e. delta up to ``+t * ref``. The CI confirms a
      regression when its **lower** bound is above that: ``ci_low > t*ref``.

    ``ci_excludes_zero`` alone is never sufficient -- the test is against the
    tolerated boundary, not zero.
    """
    if threshold is None or evidence.ci_low is None or evidence.ci_high is None:
        return False
    ref = evidence.baseline.mean
    boundary = threshold * ref
    if direction == "higher_is_better":
        return evidence.ci_high < -boundary
    return evidence.ci_low > boundary


def _adverse_phrase(verdict: MetricVerdict) -> str:
    if verdict.adverse_change is None:
        return (
            f"increased from a zero baseline to {verdict.candidate:g} "
            f"(unbounded regression; cannot be expressed as a finite percentage)"
        )
    return f"{verdict.direction.replace('_', '-')} regression of {verdict.adverse_change:.1%}"


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


def _advisory(verdict: MetricVerdict) -> str:
    """Human note for a threshold breach that did not BLOCK on statistical
    grounds -- surfaced separately from ``reasons`` so a PASS stays a PASS."""
    assert verdict.threshold is not None and verdict.evidence is not None
    ev = verdict.evidence
    head = (
        f"{verdict.metric}: observed {_adverse_phrase(verdict)} "
        f"exceeds the {verdict.threshold:.0%} limit"
    )
    if verdict.outcome == "regression_low_evidence":
        return (
            f"{head}, but only {ev.n_pairs} paired sample(s) "
            f"(minimum {MIN_PAIRS_TO_BLOCK}) -- insufficient evidence to block; "
            f"increase repeats or dataset size"
        )
    ci = "unavailable" if ev.ci_low is None else f"[{ev.ci_low:.3g}, {ev.ci_high:.3g}]"
    return (
        f"{head}, but the {ev.confidence_level:.0%} CI {ci} does not confirm a "
        f"regression beyond the tolerated boundary -- not blocking"
    )
