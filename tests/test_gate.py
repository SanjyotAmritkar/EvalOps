"""Tests for evalops.gate.evaluate_gate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.entities import EvaluationResult, ReleasePolicy
from evalops.domain.enums import ReleaseDecision
from evalops.domain.value_objects import MetricComparison
from evalops.errors import ConfigError
from evalops.gate import GateReport, evaluate_gate


def _result(*triples: tuple[str, float, float]) -> EvaluationResult:
    return EvaluationResult(
        experiment_id="exp",
        metrics=tuple(
            MetricComparison(metric=m, baseline_value=b, candidate_value=c) for m, b, c in triples
        ),
    )


def _policy(**thresholds: float) -> ReleasePolicy:
    return ReleasePolicy(name="p", thresholds=thresholds)


def _verdict(report: GateReport, metric: str) -> object:
    return next(v for v in report.verdicts if v.metric == metric)


# --- higher-is-better --------------------------------------------------------


def test_higher_is_better_improvement_passes() -> None:
    report = evaluate_gate(_result(("success_rate", 0.80, 0.90)), _policy(success_rate=0.05))

    assert report.decision is ReleaseDecision.PASS
    assert report.reasons == ()
    assert report.gated is True


def test_higher_is_better_regression_within_threshold_passes() -> None:
    report = evaluate_gate(_result(("success_rate", 1.00, 0.98)), _policy(success_rate=0.05))

    assert report.decision is ReleaseDecision.PASS


def test_higher_is_better_regression_beyond_threshold_blocks() -> None:
    report = evaluate_gate(_result(("success_rate", 1.00, 0.90)), _policy(success_rate=0.05))

    assert report.decision is ReleaseDecision.BLOCK
    assert any("success_rate" in reason for reason in report.reasons)


# --- lower-is-better --------------------------------------------------------


def test_lower_is_better_improvement_passes() -> None:
    report = evaluate_gate(
        _result(("latency_ms.p95", 100.0, 80.0)), _policy(**{"latency_ms.p95": 0.15})
    )

    assert report.decision is ReleaseDecision.PASS


def test_lower_is_better_regression_within_threshold_passes() -> None:
    report = evaluate_gate(
        _result(("latency_ms.p95", 100.0, 110.0)), _policy(**{"latency_ms.p95": 0.15})
    )

    assert report.decision is ReleaseDecision.PASS


def test_lower_is_better_regression_beyond_threshold_blocks() -> None:
    report = evaluate_gate(
        _result(("latency_ms.p95", 100.0, 140.0)), _policy(**{"latency_ms.p95": 0.15})
    )

    assert report.decision is ReleaseDecision.BLOCK


def test_threshold_boundary_equality_passes() -> None:
    # 10% drop, threshold exactly 0.10 -> adverse_change == threshold, not '>'
    report = evaluate_gate(_result(("success_rate", 1.00, 0.90)), _policy(success_rate=0.10))

    assert report.decision is ReleaseDecision.PASS


# --- zero baseline --------------------------------------------------------


def test_zero_baseline_both_zero_is_not_a_regression() -> None:
    report = evaluate_gate(
        _result(("cost_usd.total", 0.0, 0.0)), _policy(**{"cost_usd.total": 0.10})
    )

    assert report.decision is ReleaseDecision.PASS
    assert _verdict(report, "cost_usd.total").adverse_change == 0.0  # type: ignore[attr-defined]


def test_zero_baseline_higher_is_better_is_not_a_regression() -> None:
    report = evaluate_gate(_result(("success_rate", 0.0, 0.5)), _policy(success_rate=0.0))

    assert report.decision is ReleaseDecision.PASS


def test_zero_baseline_lower_is_better_blocks_with_unbounded_reason() -> None:
    report = evaluate_gate(
        _result(("latency_ms.p95", 0.0, 50.0)), _policy(**{"latency_ms.p95": 0.15})
    )

    assert report.decision is ReleaseDecision.BLOCK
    verdict = _verdict(report, "latency_ms.p95")
    assert verdict.adverse_change is None  # type: ignore[attr-defined]
    assert any("unbounded" in reason for reason in report.reasons)


# --- policy handling -------------------------------------------------------


def test_unknown_policy_metric_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="not produced by the evaluation"):
        evaluate_gate(_result(("success_rate", 1.0, 1.0)), _policy(**{"made_up.metric": 0.1}))


def test_produced_metric_absent_from_policy_is_not_gated() -> None:
    # cost regresses massively but the policy does not threshold it
    report = evaluate_gate(
        _result(("success_rate", 1.0, 1.0), ("cost_usd.total", 1.0, 100.0)),
        _policy(success_rate=0.05),
    )

    assert report.decision is ReleaseDecision.PASS
    cost = _verdict(report, "cost_usd.total")
    assert cost.threshold is None  # type: ignore[attr-defined]
    assert cost.regression is False  # type: ignore[attr-defined]


def test_no_policy_passes_ungated() -> None:
    report = evaluate_gate(
        _result(("success_rate", 1.0, 0.0), ("latency_ms.p95", 1.0, 999.0)), None
    )

    assert report.decision is ReleaseDecision.PASS
    assert report.gated is False
    assert report.reasons == ()
    assert all(v.regression is False for v in report.verdicts)


def test_multiple_regressions_produce_multiple_reasons() -> None:
    report = evaluate_gate(
        _result(("success_rate", 1.0, 0.5), ("latency_ms.p95", 100.0, 200.0)),
        _policy(success_rate=0.05, **{"latency_ms.p95": 0.15}),
    )

    assert report.decision is ReleaseDecision.BLOCK
    assert len(report.reasons) == 2


def test_any_regression_blocks_and_none_passes() -> None:
    metrics = _result(
        ("success_rate", 1.0, 1.0),
        ("latency_ms.p95", 100.0, 101.0),
        ("cost_usd.total", 1.0, 1.0),
    )
    policy = _policy(success_rate=0.05, **{"latency_ms.p95": 0.15, "cost_usd.total": 0.10})

    assert evaluate_gate(metrics, policy).decision is ReleaseDecision.PASS

    worse = _result(
        ("success_rate", 1.0, 1.0),
        ("latency_ms.p95", 100.0, 200.0),
        ("cost_usd.total", 1.0, 1.0),
    )
    assert evaluate_gate(worse, policy).decision is ReleaseDecision.BLOCK


def test_gate_report_is_immutable() -> None:
    report = evaluate_gate(_result(("success_rate", 1.0, 1.0)), None)

    with pytest.raises(FrozenInstanceError):
        report.decision = ReleaseDecision.BLOCK  # type: ignore[misc]
