"""CP 5.2 statistical release gating: evaluate_gate reading EvaluationResult.evidence.

The policy threshold still defines the tolerated effect; paired-bootstrap
evidence only stops weak/noisy/inconclusive breaches from BLOCKing. Metrics
without evidence (latency_ms.p95, cost_usd.total) keep the deterministic gate.
"""

from __future__ import annotations

import pytest

from evalops.domain.entities import EvaluationResult, ReleasePolicy
from evalops.domain.enums import ReleaseDecision
from evalops.domain.value_objects import MetricComparison, MetricEvidence, MetricKind, SampleSummary
from evalops.gate import MIN_PAIRS_TO_BLOCK, GateReport, MetricVerdict, evaluate_gate


def _summary(n: int, mean: float) -> SampleSummary:
    return SampleSummary(n=n, mean=mean, median=mean, stdev=0.0)


def _evidence(
    metric: str,
    *,
    n_pairs: int,
    baseline_mean: float,
    delta: float,
    ci: tuple[float, float] | None,
    kind: MetricKind = "binary",
    insufficient: bool = False,
) -> MetricEvidence:
    ci_low, ci_high = (None, None) if ci is None else ci
    return MetricEvidence(
        metric=metric,
        kind=kind,
        n_pairs=n_pairs,
        baseline=_summary(n_pairs, baseline_mean),
        candidate=_summary(n_pairs, baseline_mean + delta),
        paired_delta=_summary(n_pairs, delta),
        delta=delta,
        relative_change=None if baseline_mean == 0 else delta / baseline_mean,
        confidence_level=0.95,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_excludes_zero=ci is not None and (ci_low > 0.0 or ci_high < 0.0),  # type: ignore[operator]
        insufficient_evidence=insufficient,
        method="paired_bootstrap_percentile",
        resamples=2000,
        seed=1,
    )


def _result(
    metrics: list[tuple[str, float, float]],
    evidence: list[MetricEvidence] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        experiment_id="exp",
        metrics=tuple(MetricComparison(m, b, c) for m, b, c in metrics),
        evidence=tuple(evidence or ()),
    )


def _policy(**thresholds: float) -> ReleasePolicy:
    return ReleasePolicy(name="p", thresholds=thresholds)


def _verdict(report: GateReport, metric: str) -> MetricVerdict:
    return next(v for v in report.verdicts if v.metric == metric)


# --- statistically supported regression -> BLOCK ------------------------


def test_clear_adverse_regression_with_confirming_ci_blocks() -> None:
    # success_rate drops 40% (limit 10%); CI [-0.5, -0.35] is entirely past the
    # -10% tolerated boundary -> BLOCK.
    ev = _evidence("success_rate", n_pairs=12, baseline_mean=1.0, delta=-0.4, ci=(-0.5, -0.35))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.6)], [ev]), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.BLOCK
    assert any("success_rate" in r for r in report.reasons)
    assert report.advisories == ()
    v = _verdict(report, "success_rate")
    assert v.outcome == "regression" and v.regression is True and v.threshold_breached is True


def test_lower_is_better_regression_with_confirming_ci_blocks() -> None:
    # latency mean +50% (limit 20%); delta CI [40, 60] all above the +20 boundary.
    ev = _evidence(
        "latency_ms.mean",
        n_pairs=10,
        baseline_mean=100.0,
        delta=50.0,
        ci=(40.0, 60.0),
        kind="continuous",
    )
    report = evaluate_gate(
        _result([("latency_ms.mean", 100.0, 150.0)], [ev]),
        _policy(**{"latency_ms.mean": 0.20}),
    )

    assert report.decision is ReleaseDecision.BLOCK
    assert _verdict(report, "latency_ms.mean").outcome == "regression"


# --- breach but statistically inconclusive -> PASS + advisory ---------


def test_noisy_breach_with_ci_spanning_the_boundary_does_not_block() -> None:
    # same 40% point drop, but CI [-0.85, 0.05] crosses the -10% boundary.
    ev = _evidence("success_rate", n_pairs=12, baseline_mean=1.0, delta=-0.4, ci=(-0.85, 0.05))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.6)], [ev]), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.PASS
    assert report.reasons == ()
    assert any("success_rate" in a and "not blocking" in a for a in report.advisories)
    v = _verdict(report, "success_rate")
    assert v.outcome == "regression_inconclusive"
    assert v.threshold_breached is True and v.regression is False


def test_ci_excluding_zero_but_inside_tolerance_does_not_block() -> None:
    # 15% point drop (limit 10%); CI [-0.20, -0.05] excludes zero yet the
    # candidate may be only 5% worse -- within tolerance -> not blocking.
    ev = _evidence("success_rate", n_pairs=20, baseline_mean=1.0, delta=-0.15, ci=(-0.20, -0.05))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.85)], [ev]), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.PASS
    assert _verdict(report, "success_rate").outcome == "regression_inconclusive"


# --- insufficient evidence -> PASS + advisory ------------------------


def test_confirming_ci_but_too_few_pairs_does_not_block() -> None:
    ev = _evidence(
        "success_rate",
        n_pairs=MIN_PAIRS_TO_BLOCK - 1,
        baseline_mean=1.0,
        delta=-0.4,
        ci=(-0.5, -0.35),
    )
    report = evaluate_gate(_result([("success_rate", 1.0, 0.6)], [ev]), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.PASS
    assert _verdict(report, "success_rate").outcome == "regression_low_evidence"
    assert any("insufficient evidence" in a for a in report.advisories)


def test_no_ci_at_all_does_not_block() -> None:
    ev = _evidence(
        "success_rate", n_pairs=2, baseline_mean=1.0, delta=-1.0, ci=None, insufficient=True
    )
    report = evaluate_gate(_result([("success_rate", 1.0, 0.0)], [ev]), _policy(success_rate=0.0))

    assert report.decision is ReleaseDecision.PASS
    assert _verdict(report, "success_rate").outcome == "regression_low_evidence"


# --- tolerated change -> PASS, no advisory ---------------------------


def test_change_within_threshold_passes_regardless_of_evidence() -> None:
    ev = _evidence("success_rate", n_pairs=30, baseline_mean=1.0, delta=-0.05, ci=(-0.06, -0.04))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.95)], [ev]), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.PASS
    assert report.advisories == ()
    v = _verdict(report, "success_rate")
    assert v.outcome == "pass" and v.threshold_breached is False


# --- deterministic metrics keep the old behaviour --------------------


def test_metric_without_evidence_gates_deterministically() -> None:
    # latency_ms.p95 has no MetricEvidence -> a threshold breach still BLOCKs.
    report = evaluate_gate(
        _result([("latency_ms.p95", 100.0, 150.0)]),
        _policy(**{"latency_ms.p95": 0.20}),
    )
    assert report.decision is ReleaseDecision.BLOCK
    assert any("latency_ms.p95" in r for r in report.reasons)
    assert _verdict(report, "latency_ms.p95").outcome == "regression"


def test_deterministic_breach_blocks_even_when_statistical_metric_is_inconclusive() -> None:
    lat_mean_ev = _evidence(
        "latency_ms.mean",
        n_pairs=12,
        baseline_mean=100.0,
        delta=50.0,
        ci=(-10.0, 110.0),
        kind="continuous",  # spans the +20 boundary
    )
    report = evaluate_gate(
        _result(
            [("latency_ms.mean", 100.0, 150.0), ("latency_ms.p95", 100.0, 150.0)],
            [lat_mean_ev],
        ),
        _policy(**{"latency_ms.mean": 0.20, "latency_ms.p95": 0.20}),
    )

    assert report.decision is ReleaseDecision.BLOCK
    assert [v.metric for v in report.verdicts if v.regression] == ["latency_ms.p95"]
    assert any("latency_ms.mean" in a for a in report.advisories)


def test_evidence_free_result_is_purely_deterministic_backward_compatible() -> None:
    # No evidence at all (pre-Phase-5 shape): a breach blocks, exactly as before.
    report = evaluate_gate(_result([("success_rate", 1.0, 0.5)]), _policy(success_rate=0.05))
    assert report.decision is ReleaseDecision.BLOCK
    assert _verdict(report, "success_rate").outcome == "regression"
    assert report.advisories == ()


def test_no_policy_never_blocks_and_emits_no_advisories() -> None:
    ev = _evidence("success_rate", n_pairs=12, baseline_mean=1.0, delta=-0.4, ci=(-0.5, -0.35))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.6)], [ev]), None)

    assert report.decision is ReleaseDecision.PASS
    assert report.gated is False
    assert report.reasons == () and report.advisories == ()


def test_higher_and_lower_is_better_boundaries_are_symmetric() -> None:
    # higher-is-better: adverse is a DROP; confirm needs ci_high < -t*ref.
    hib = _evidence("success_rate", n_pairs=12, baseline_mean=1.0, delta=-0.3, ci=(-0.35, -0.25))
    hib_report = evaluate_gate(
        _result([("success_rate", 1.0, 0.7)], [hib]), _policy(success_rate=0.10)
    )
    assert hib_report.decision is ReleaseDecision.BLOCK

    # lower-is-better: adverse is a RISE; confirm needs ci_low > t*ref.
    lib = _evidence(
        "latency_ms.mean",
        n_pairs=12,
        baseline_mean=200.0,
        delta=60.0,
        ci=(50.0, 70.0),
        kind="continuous",
    )
    lib_report = evaluate_gate(
        _result([("latency_ms.mean", 200.0, 260.0)], [lib]),
        _policy(**{"latency_ms.mean": 0.10}),  # boundary +20
    )
    assert lib_report.decision is ReleaseDecision.BLOCK

    # ...and the mirror image just inside the boundary does NOT block.
    lib_ok = _evidence(
        "latency_ms.mean",
        n_pairs=12,
        baseline_mean=200.0,
        delta=60.0,
        ci=(5.0, 120.0),
        kind="continuous",  # ci_low 5 < 20 boundary
    )
    ok_report = evaluate_gate(
        _result([("latency_ms.mean", 200.0, 260.0)], [lib_ok]),
        _policy(**{"latency_ms.mean": 0.10}),
    )
    assert ok_report.decision is ReleaseDecision.PASS
    assert _verdict(ok_report, "latency_ms.mean").outcome == "regression_inconclusive"


def test_improvement_never_produces_a_reason_or_advisory() -> None:
    ev = _evidence("success_rate", n_pairs=12, baseline_mean=0.8, delta=0.15, ci=(0.10, 0.20))
    report = evaluate_gate(_result([("success_rate", 0.8, 0.95)], [ev]), _policy(success_rate=0.10))
    assert report.decision is ReleaseDecision.PASS
    assert report.reasons == () and report.advisories == ()
    assert _verdict(report, "success_rate").outcome == "pass"


@pytest.mark.parametrize("n_pairs", [MIN_PAIRS_TO_BLOCK, MIN_PAIRS_TO_BLOCK + 5])
def test_min_pairs_boundary_is_inclusive(n_pairs: int) -> None:
    ev = _evidence("success_rate", n_pairs=n_pairs, baseline_mean=1.0, delta=-0.4, ci=(-0.5, -0.35))
    report = evaluate_gate(_result([("success_rate", 1.0, 0.6)], [ev]), _policy(success_rate=0.10))
    assert report.decision is ReleaseDecision.BLOCK  # exactly MIN_PAIRS_TO_BLOCK is enough
