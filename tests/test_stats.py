"""Tests for evalops.stats: paired observations, summaries, paired bootstrap CI."""

from __future__ import annotations

import statistics
from collections.abc import Mapping

import pytest

from evalops.domain.contracts import ProviderClient, ProviderResponse
from evalops.domain.entities import (
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationRun,
    Experiment,
    SystemVersion,
)
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics
from evalops.errors import ConfigError
from evalops.evaluators import Contains
from evalops.execution import run_evaluation
from evalops.runner import RunOutcome
from evalops.stats import (
    MIN_PAIRS_FOR_CI,
    build_statistical_evidence,
    metric_evidence,
    paired_bootstrap_ci,
    paired_observations,
    summarize,
)

EXPERIMENT = Experiment(
    project_id="p",
    dataset_id="d",
    baseline_version_id="base",
    candidate_version_id="cand",
)


def _run(
    version_id: str,
    *,
    case_id: str,
    repeat: int,
    error: str | None = None,
    latency: float = 0.0,
    cost: float = 0.0,
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


def _outcome(
    *pairs: tuple[EvaluationRun, tuple[EvaluatorScore, ...]],
) -> RunOutcome:
    runs = tuple(run for run, _ in pairs)
    results = tuple(CaseResult(run_id=run.id, scores=scores) for run, scores in pairs)
    return RunOutcome(runs=runs, case_results=results)


# --- descriptive summaries ---------------------------------------------


def test_summarize_reports_n_mean_median_sample_stdev() -> None:
    s = summarize([1.0, 2.0, 3.0, 4.0])
    assert s.n == 4
    assert s.mean == 2.5
    assert s.median == 2.5
    assert s.stdev == pytest.approx(statistics.stdev([1.0, 2.0, 3.0, 4.0]))


def test_summarize_handles_tiny_and_empty_series() -> None:
    assert summarize([]) == summarize([])  # n == 0, all zeros, no crash
    assert summarize([]).n == 0
    one = summarize([7.0])
    assert (one.n, one.mean, one.median, one.stdev) == (1, 7.0, 7.0, 0.0)


# --- paired matching -------------------------------------------------


def test_pairs_use_only_matching_keys_in_deterministic_order() -> None:
    # baseline keys: (c0,0),(c0,1),(c1,0); candidate keys: (c0,0),(c0,1),(c2,0)
    outcome = _outcome(
        (_run("base", case_id="c1", repeat=0, latency=5.0), ()),  # deliberately unordered
        (_run("base", case_id="c0", repeat=1, latency=2.0), ()),
        (_run("base", case_id="c0", repeat=0, latency=1.0), ()),
        (_run("cand", case_id="c2", repeat=0, latency=9.0), ()),
        (_run("cand", case_id="c0", repeat=0, latency=3.0), ()),
        (_run("cand", case_id="c0", repeat=1, latency=4.0), ()),
    )

    lat = paired_observations(EXPERIMENT, outcome, evaluator_names=[])["latency_ms.mean"]

    assert lat.matched_pairs == 2  # (c0,0) and (c0,1)
    assert lat.baseline == (1.0, 2.0)  # ordered by (case_id, repeat_index)
    assert lat.candidate == (3.0, 4.0)
    assert lat.unmatched_runs == 2  # base (c1,0) and cand (c2,0)


def test_duplicate_pair_key_within_a_version_is_rejected() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), ()),
        (_run("base", case_id="c0", repeat=0), ()),  # duplicate (case, repeat)
        (_run("cand", case_id="c0", repeat=0), ()),
    )
    with pytest.raises(ConfigError, match="more than one run"):
        paired_observations(EXPERIMENT, outcome, evaluator_names=[])


# --- binary metrics -------------------------------------------------


def test_success_rate_is_binary_and_keeps_failed_pairs() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), ()),
        (_run("base", case_id="c0", repeat=1, error="boom"), ()),
        (_run("cand", case_id="c0", repeat=0), ()),
        (_run("cand", case_id="c0", repeat=1), ()),
    )

    s = paired_observations(EXPERIMENT, outcome, evaluator_names=[])["success_rate"]

    assert s.kind == "binary"
    assert s.baseline == (1.0, 0.0)  # the errored baseline run contributes 0.0
    assert s.candidate == (1.0, 1.0)
    assert (s.comparable_pairs, s.dropped_provider_failures) == (2, 0)


def test_pass_rate_observations_are_binary_with_failed_as_zero() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), (_score("m", passed=True),)),
        (_run("base", case_id="c0", repeat=1, error="boom"), ()),
        (_run("cand", case_id="c0", repeat=0), (_score("m", passed=False),)),
        (_run("cand", case_id="c0", repeat=1), (_score("m", passed=True),)),
    )

    s = paired_observations(EXPERIMENT, outcome, evaluator_names=["m"])["m.pass_rate"]

    assert s.kind == "binary"
    assert s.baseline == (1.0, 0.0)
    assert s.candidate == (0.0, 1.0)


def test_missing_evaluator_score_on_a_successful_run_is_rejected() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0), (_score("m", passed=True),)),
        (_run("cand", case_id="c0", repeat=0), ()),  # successful, no scores
    )
    with pytest.raises(ConfigError, match="missing the 'm' evaluator score"):
        paired_observations(EXPERIMENT, outcome, evaluator_names=["m"])


# --- continuous metrics + provider-failure semantics -----------------


def test_latency_drops_pairs_where_either_side_failed_cost_keeps_them() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0, latency=10.0, cost=0.01), ()),
        (_run("base", case_id="c0", repeat=1, latency=20.0, cost=0.01), ()),
        (_run("cand", case_id="c0", repeat=0, latency=11.0, cost=0.02), ()),
        (_run("cand", case_id="c0", repeat=1, error="boom", cost=0.0), ()),
    )

    series = paired_observations(EXPERIMENT, outcome, evaluator_names=[])

    lat = series["latency_ms.mean"]
    assert lat.kind == "continuous"
    assert lat.baseline == (10.0,) and lat.candidate == (11.0,)
    assert (lat.matched_pairs, lat.comparable_pairs, lat.dropped_provider_failures) == (2, 1, 1)

    cost = series["cost_usd.mean"]
    assert cost.comparable_pairs == 2  # a failed run genuinely costs ~0
    assert cost.baseline == (0.01, 0.01) and cost.candidate == (0.02, 0.0)


# --- deterministic bootstrap ---------------------------------------


def test_paired_bootstrap_ci_is_deterministic_and_a_proper_interval() -> None:
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    cand = [1.5, 2.4, 3.6, 4.1, 5.9, 6.3]

    first = paired_bootstrap_ci(base, cand, seed=123, resamples=500)
    second = paired_bootstrap_ci(base, cand, seed=123, resamples=500)

    assert first == second  # same seed -> identical interval
    lo, hi = first
    assert lo is not None and hi is not None and lo < hi
    # a different seed still yields a valid, usually different interval
    other_lo, other_hi = paired_bootstrap_ci(base, cand, seed=999, resamples=500)
    assert other_lo is not None and other_hi is not None and other_lo <= other_hi


def test_wider_confidence_level_gives_a_wider_interval() -> None:
    base = [1.0, 2, 3, 4, 5, 6, 7, 8]
    cand = [1.4, 2.1, 3.7, 4.2, 5.1, 6.9, 7.3, 8.6]

    lo90, hi90 = paired_bootstrap_ci(base, cand, confidence_level=0.90, seed=11, resamples=800)
    lo99, hi99 = paired_bootstrap_ci(base, cand, confidence_level=0.99, seed=11, resamples=800)

    assert lo90 is not None and hi90 is not None
    assert lo99 is not None and hi99 is not None
    assert (hi99 - lo99) >= (hi90 - lo90)


def test_confidence_level_out_of_range_is_rejected() -> None:
    with pytest.raises(ConfigError, match="confidence_level"):
        paired_bootstrap_ci([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0], confidence_level=1.5)


# --- confidence interval direction -------------------------------


def test_ci_excludes_zero_for_a_consistent_shift() -> None:
    base = [10.0] * 8
    cand = [12.0, 11.5, 12.5, 11.8, 12.2, 11.9, 12.1, 12.3]  # every pair worse

    ev = metric_evidence("latency_ms.mean", "continuous", base, cand, resamples=1000, seed=1)

    assert ev.delta > 0.0
    assert ev.ci_low is not None and ev.ci_low > 0.0
    assert ev.ci_excludes_zero is True
    assert ev.insufficient_evidence is False


def test_ci_spans_zero_for_symmetric_noise() -> None:
    base = [5.0] * 8
    cand = [5.5, 4.5, 5.4, 4.6, 5.3, 4.7, 5.2, 4.8]  # mean exactly 5.0

    ev = metric_evidence("latency_ms.mean", "continuous", base, cand, resamples=1000, seed=2)

    assert ev.delta == pytest.approx(0.0)
    assert ev.ci_low is not None and ev.ci_high is not None
    assert ev.ci_low < 0.0 < ev.ci_high
    assert ev.ci_excludes_zero is False


# --- zero baseline / constant values ---------------------------


def test_zero_baseline_yields_none_relative_change() -> None:
    ev = metric_evidence(
        "success_rate", "binary", [0.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 1.0], resamples=200, seed=3
    )
    assert ev.baseline.mean == 0.0
    assert ev.relative_change is None
    assert ev.delta == 0.5


def test_constant_zero_difference_collapses_ci_to_zero() -> None:
    ev = metric_evidence("cost_usd.mean", "continuous", [2.0] * 5, [2.0] * 5, resamples=200, seed=4)
    assert ev.paired_delta.stdev == 0.0
    assert (ev.ci_low, ev.ci_high) == (0.0, 0.0)
    assert ev.ci_excludes_zero is False


def test_constant_nonzero_difference_collapses_ci_to_that_point() -> None:
    ev = metric_evidence(
        "cost_usd.mean", "continuous", [1.0] * 4, [1.25] * 4, resamples=200, seed=5
    )
    assert (ev.ci_low, ev.ci_high) == (0.25, 0.25)
    assert ev.ci_excludes_zero is True
    assert ev.insufficient_evidence is False
    assert ev.relative_change == pytest.approx(0.25)


# --- insufficient sample -------------------------------------


@pytest.mark.parametrize("n", [0, 1, 2])
def test_too_few_pairs_report_point_estimate_but_no_interval(n: int) -> None:
    ev = metric_evidence("latency_ms.mean", "continuous", [1.0] * n, [2.0] * n, seed=6)

    assert n < MIN_PAIRS_FOR_CI
    assert ev.n_pairs == n
    assert ev.insufficient_evidence is True
    assert ev.ci_low is None and ev.ci_high is None
    assert ev.ci_excludes_zero is False
    if n:
        assert ev.delta == 1.0


# --- build_statistical_evidence over a RunOutcome -----------------


def test_build_statistical_evidence_covers_gateable_metrics_in_order() -> None:
    def _b(
        case: str, repeat: int, latency: float, passed: bool
    ) -> tuple[EvaluationRun, tuple[EvaluatorScore, ...]]:
        run = _run("base", case_id=case, repeat=repeat, latency=latency, cost=0.01)
        return run, (_score("m", passed=passed),)

    def _c(
        case: str, repeat: int, latency: float, passed: bool
    ) -> tuple[EvaluationRun, tuple[EvaluatorScore, ...]]:
        run = _run("cand", case_id=case, repeat=repeat, latency=latency, cost=0.02)
        return run, (_score("m", passed=passed),)

    outcome = _outcome(
        _b("c0", 0, 10.0, True),
        _b("c0", 1, 11.0, True),
        _b("c1", 0, 12.0, False),
        _c("c0", 0, 20.0, True),
        _c("c0", 1, 21.0, True),
        _c("c1", 0, 22.0, True),
    )

    evidence = build_statistical_evidence(
        EXPERIMENT, outcome, evaluator_names=["m"], resamples=200, seed=7
    )

    assert [e.metric for e in evidence] == [
        "success_rate",
        "m.pass_rate",
        "latency_ms.mean",
        "cost_usd.mean",
    ]
    lat = next(e for e in evidence if e.metric == "latency_ms.mean")
    assert lat.kind == "continuous"
    assert lat.n_pairs == 3
    assert lat.delta == pytest.approx(10.0)
    assert lat.confidence_level == 0.95
    sr = next(e for e in evidence if e.metric == "success_rate")
    assert sr.kind == "binary"


def test_build_statistical_evidence_is_deterministic() -> None:
    outcome = _outcome(
        *(
            (_run(v, case_id=f"c{c}", repeat=r, latency=float(10 + c + r + off)), ())
            for v, off in (("base", 0), ("cand", 3))
            for c in range(3)
            for r in range(2)
        )
    )
    a = build_statistical_evidence(EXPERIMENT, outcome, evaluator_names=[], resamples=300, seed=9)
    b = build_statistical_evidence(EXPERIMENT, outcome, evaluator_names=[], resamples=300, seed=9)
    assert a == b


def test_evidence_reports_dropped_provider_failures() -> None:
    outcome = _outcome(
        (_run("base", case_id="c0", repeat=0, latency=10.0), ()),
        (_run("base", case_id="c0", repeat=1, latency=10.0), ()),
        (_run("base", case_id="c0", repeat=2, latency=10.0), ()),
        (_run("cand", case_id="c0", repeat=0, latency=12.0), ()),
        (_run("cand", case_id="c0", repeat=1, latency=12.0), ()),
        (_run("cand", case_id="c0", repeat=2, error="boom"), ()),
    )

    lat = next(
        e
        for e in build_statistical_evidence(
            EXPERIMENT, outcome, evaluator_names=[], resamples=100, seed=8
        )
        if e.metric == "latency_ms.mean"
    )
    assert lat.dropped_provider_failures == 1
    assert lat.n_pairs == 2
    assert lat.insufficient_evidence is True  # only 2 comparable pairs left


# --- wiring: run_evaluation attaches evidence, result/gate unchanged ---


class _Provider:
    name = "openai"

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        return ProviderResponse(text="ok", usage=UsageMetrics(latency_ms=5.0, cost_usd=0.001))


def test_run_evaluation_attaches_evidence_without_touching_result_or_gate() -> None:
    base = SystemVersion(
        project_id="p",
        name="c",
        version="b",
        provider=ProviderName.OPENAI,
        model="m",
        prompt_template="P: ${input}",
    )
    cand = SystemVersion(
        project_id="p",
        name="c",
        version="c",
        provider=ProviderName.OPENAI,
        model="m",
        prompt_template="P: ${input}",
    )
    ds = Dataset(
        project_id="p",
        name="d",
        version=1,
        cases=(DatasetCase(input="x", expected_output="ok", id="c0"),),
    )
    exp = Experiment(
        project_id="p",
        dataset_id=ds.id,
        baseline_version_id=base.id,
        candidate_version_id=cand.id,
        repeats=4,
    )
    evaluators = [Contains(name="contains", case_sensitive=False)]
    providers: Mapping[ProviderName, ProviderClient] = {ProviderName.OPENAI: _Provider()}

    ev = run_evaluation(exp, ds, base, cand, None, evaluators=evaluators, providers=providers)

    # Phase 1 aggregation output is untouched
    assert [m.metric for m in ev.result.metrics] == [
        "success_rate",
        "contains.pass_rate",
        "latency_ms.mean",
        "latency_ms.p95",
        "cost_usd.total",
    ]
    assert ev.gate.gated is False  # no policy supplied

    # additive statistical evidence, in aggregation order (p95 / total excluded)
    assert [e.metric for e in ev.evidence] == [
        "success_rate",
        "contains.pass_rate",
        "latency_ms.mean",
        "cost_usd.mean",
    ]
    lat = next(e for e in ev.evidence if e.metric == "latency_ms.mean")
    assert lat.n_pairs == 4  # 1 case x 4 repeats
    assert lat.kind == "continuous"
    assert lat.delta == pytest.approx(0.0)  # identical provider both sides
    assert lat.ci_excludes_zero is False
