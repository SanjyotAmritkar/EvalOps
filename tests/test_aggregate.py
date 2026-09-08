"""Tests for evalops.aggregate.aggregate_results."""

from __future__ import annotations

import pytest

from evalops.aggregate import aggregate_results
from evalops.domain.entities import CaseResult, EvaluationResult, EvaluationRun, Experiment
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import EvaluatorScore, MetricComparison, UsageMetrics
from evalops.errors import ConfigError
from evalops.runner import RunOutcome

EXPERIMENT = Experiment(
    project_id="p",
    dataset_id="d",
    baseline_version_id="base",
    candidate_version_id="cand",
)


def _run(
    version_id: str,
    *,
    error: str | None = None,
    latency: float = 0.0,
    cost: float = 0.0,
    case_id: str = "c0",
    repeat: int = 0,
) -> EvaluationRun:
    return EvaluationRun(
        experiment_id=EXPERIMENT.id,
        system_version_id=version_id,
        case_id=case_id,
        repeat_index=repeat,
        output="" if error else "out",
        usage=UsageMetrics(latency_ms=latency, cost_usd=cost),
        error=error,
    )


def _score(name: str, *, passed: bool) -> EvaluatorScore:
    return EvaluatorScore(
        evaluator=name,
        family=EvaluatorFamily.DETERMINISTIC,
        score=1.0 if passed else 0.0,
        passed=passed,
    )


def _outcome(*pairs: tuple[EvaluationRun, tuple[EvaluatorScore, ...]]) -> RunOutcome:
    runs = tuple(run for run, _ in pairs)
    results = tuple(CaseResult(run_id=run.id, scores=scores) for run, scores in pairs)
    return RunOutcome(runs=runs, case_results=results)


def _metric(result: EvaluationResult, name: str) -> MetricComparison:
    return next(m for m in result.metrics if m.metric == name)


def _aggregate(outcome: RunOutcome, names: list[str]) -> EvaluationResult:
    return aggregate_results(EXPERIMENT, outcome, evaluator_names=names)


def test_success_rate_counts_non_error_runs() -> None:
    outcome = _outcome(
        (_run("base"), ()),
        (_run("base"), ()),
        (_run("cand"), ()),
        (_run("cand", error="boom"), ()),
    )

    result = _aggregate(outcome, [])
    success = _metric(result, "success_rate")

    assert success.baseline_value == 1.0
    assert success.candidate_value == 0.5


def test_failed_runs_are_in_the_pass_rate_denominator() -> None:
    outcome = _outcome(
        (_run("base"), (_score("exact_match", passed=True),)),
        (_run("base", error="boom"), ()),
        (_run("cand"), (_score("exact_match", passed=True),)),
        (_run("cand"), (_score("exact_match", passed=True),)),
    )

    result = _aggregate(outcome, ["exact_match"])
    pass_rate = _metric(result, "exact_match.pass_rate")

    assert pass_rate.baseline_value == 0.5  # 1 passed / 2 runs (one failed)
    assert pass_rate.candidate_value == 1.0


def test_multiple_evaluators_produce_separate_pass_rate_metrics() -> None:
    outcome = _outcome(
        (_run("base"), (_score("a", passed=True), _score("b", passed=False))),
        (_run("cand"), (_score("a", passed=True), _score("b", passed=True))),
    )

    result = _aggregate(outcome, ["a", "b"])

    assert _metric(result, "a.pass_rate").baseline_value == 1.0
    assert _metric(result, "b.pass_rate").baseline_value == 0.0
    assert _metric(result, "b.pass_rate").candidate_value == 1.0


def test_latency_mean_uses_successful_runs_only() -> None:
    outcome = _outcome(
        (_run("base", latency=10.0), ()),
        (_run("base", latency=20.0), ()),
        (_run("base", error="boom", latency=0.0), ()),
        (_run("cand", latency=5.0), ()),
    )

    result = _aggregate(outcome, [])

    assert _metric(result, "latency_ms.mean").baseline_value == 15.0


def test_nearest_rank_p95() -> None:
    base = [_run("base", latency=float(i)) for i in range(1, 21)]  # 1..20
    cand = [_run("cand", latency=float(i)) for i in (10, 20, 30)]
    outcome = _outcome(*((r, ()) for r in [*base, *cand]))

    result = _aggregate(outcome, [])

    # n=20 -> ceil(19.0)-1 = 18 -> sorted[18] == 19.0
    assert _metric(result, "latency_ms.p95").baseline_value == 19.0
    # n=3 -> ceil(2.85)-1 = 2 -> sorted[2] == 30.0
    assert _metric(result, "latency_ms.p95").candidate_value == 30.0


def test_zero_successful_runs_give_zero_latency() -> None:
    outcome = _outcome(
        (_run("base", error="boom"), ()),
        (_run("cand", latency=9.0), ()),
    )

    result = _aggregate(outcome, [])

    assert _metric(result, "latency_ms.mean").baseline_value == 0.0
    assert _metric(result, "latency_ms.p95").baseline_value == 0.0


def test_cost_total_sums_every_run() -> None:
    outcome = _outcome(
        (_run("base", cost=0.01), ()),
        (_run("base", cost=0.02), ()),
        (_run("base", error="boom", cost=0.0), ()),
        (_run("cand", cost=0.10), ()),
    )

    result = _aggregate(outcome, [])

    assert _metric(result, "cost_usd.total").baseline_value == pytest.approx(0.03)
    assert _metric(result, "cost_usd.total").candidate_value == pytest.approx(0.10)


def test_baseline_and_candidate_are_separated() -> None:
    outcome = _outcome(
        (_run("base", latency=100.0), ()),
        (_run("cand", latency=1.0), ()),
    )

    result = _aggregate(outcome, [])
    latency = _metric(result, "latency_ms.mean")

    assert (latency.baseline_value, latency.candidate_value) == (100.0, 1.0)


def test_repeats_are_aggregated() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), (_score("a", passed=True),)),
        (_run("base", case_id="c0", repeat=1), (_score("a", passed=True),)),
        (_run("base", case_id="c0", repeat=2), (_score("a", passed=False),)),
        (_run("cand", case_id="c0", repeat=0), (_score("a", passed=True),)),
    )

    result = _aggregate(outcome, ["a"])

    assert _metric(result, "a.pass_rate").baseline_value == pytest.approx(2 / 3)


def test_result_is_an_evaluation_result_with_unique_metrics() -> None:
    outcome = _outcome(
        (_run("base"), (_score("a", passed=True),)),
        (_run("cand"), (_score("a", passed=True),)),
    )

    result = _aggregate(outcome, ["a"])

    assert isinstance(result, EvaluationResult)
    assert result.experiment_id == EXPERIMENT.id
    names = [m.metric for m in result.metrics]
    assert names == [
        "success_rate",
        "a.pass_rate",
        "latency_ms.mean",
        "latency_ms.p95",
        "cost_usd.total",
    ]
    assert len(names) == len(set(names))


def test_length_misalignment_is_rejected() -> None:
    run_a, run_b = _run("base"), _run("cand")
    outcome = RunOutcome(
        runs=(run_a, run_b),
        case_results=(CaseResult(run_id=run_a.id, scores=()),),
    )

    with pytest.raises(ConfigError, match="runs but"):
        _aggregate(outcome, [])


def test_run_id_misalignment_is_rejected() -> None:
    run_a, run_b = _run("base"), _run("cand")
    outcome = RunOutcome(
        runs=(run_a, run_b),
        case_results=(
            CaseResult(run_id=run_a.id, scores=()),
            CaseResult(run_id="not-run-b", scores=()),
        ),
    )

    with pytest.raises(ConfigError, match="misaligned"):
        _aggregate(outcome, [])


def test_missing_evaluator_score_on_success_is_rejected() -> None:
    outcome = _outcome(
        (_run("base"), (_score("a", passed=True),)),
        (_run("cand"), ()),  # successful run, no scores
    )

    with pytest.raises(ConfigError, match="missing evaluator score"):
        _aggregate(outcome, ["a"])


def test_unexpected_system_version_id_is_rejected() -> None:
    outcome = _outcome((_run("base"), ()), (_run("stranger"), ()))

    with pytest.raises(ConfigError, match="unexpected system_version_id"):
        _aggregate(outcome, [])


def test_wrong_experiment_id_is_rejected() -> None:
    stray = EvaluationRun(
        experiment_id="other-exp",
        system_version_id="base",
        case_id="c0",
        repeat_index=0,
        output="out",
    )
    outcome = _outcome((_run("cand"), ()), (stray, ()))

    with pytest.raises(ConfigError, match="experiment_id"):
        _aggregate(outcome, [])


def test_empty_candidate_side_is_rejected() -> None:
    outcome = _outcome((_run("base"), ()), (_run("base"), ()))

    with pytest.raises(ConfigError, match="no runs for candidate"):
        _aggregate(outcome, [])
