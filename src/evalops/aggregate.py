"""Experiment-level aggregation of a RunOutcome into an EvaluationResult.

Phase 1 produces a small, fixed set of plain-arithmetic metrics per version
(baseline, candidate). No confidence intervals, significance, variance, effect
sizes, or historical baselines.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from evalops.domain.entities import CaseResult, EvaluationResult, EvaluationRun, Experiment
from evalops.domain.value_objects import MetricComparison
from evalops.errors import ConfigError
from evalops.runner import RunOutcome


def aggregate_results(
    experiment: Experiment,
    outcome: RunOutcome,
    *,
    evaluator_names: Sequence[str],
) -> EvaluationResult:
    """Aggregate ``outcome`` into an ``EvaluationResult`` for ``experiment``.

    Runs are partitioned into baseline and candidate by ``system_version_id``
    (using the ids the ``Experiment`` declares). ``evaluator_names`` is the
    configured evaluator list -- passed in explicitly so pass-rate metrics do
    not depend on whichever runs happened to succeed.
    """
    _validate_outcome(experiment, outcome, evaluator_names)

    baseline_id = experiment.baseline_version_id
    candidate_id = experiment.candidate_version_id
    baseline_runs = [r for r in outcome.runs if r.system_version_id == baseline_id]
    candidate_runs = [r for r in outcome.runs if r.system_version_id == candidate_id]
    if not baseline_runs:
        raise ConfigError(f"no runs for baseline version {baseline_id!r}")
    if not candidate_runs:
        raise ConfigError(f"no runs for candidate version {candidate_id!r}")

    results_by_run = {cr.run_id: cr for cr in outcome.case_results}

    metrics: list[MetricComparison] = [
        MetricComparison(
            metric="success_rate",
            baseline_value=_success_rate(baseline_runs),
            candidate_value=_success_rate(candidate_runs),
        )
    ]
    for name in evaluator_names:
        metrics.append(
            MetricComparison(
                metric=f"{name}.pass_rate",
                baseline_value=_pass_rate(baseline_runs, results_by_run, name),
                candidate_value=_pass_rate(candidate_runs, results_by_run, name),
            )
        )
    metrics += [
        MetricComparison(
            metric="latency_ms.mean",
            baseline_value=_latency_mean(baseline_runs),
            candidate_value=_latency_mean(candidate_runs),
        ),
        MetricComparison(
            metric="latency_ms.p95",
            baseline_value=_latency_p95(baseline_runs),
            candidate_value=_latency_p95(candidate_runs),
        ),
        MetricComparison(
            metric="cost_usd.total",
            baseline_value=_cost_total(baseline_runs),
            candidate_value=_cost_total(candidate_runs),
        ),
    ]
    return EvaluationResult(experiment_id=experiment.id, metrics=tuple(metrics))


def _success_rate(runs: Sequence[EvaluationRun]) -> float:
    if not runs:
        return 0.0
    return sum(1 for r in runs if r.error is None) / len(runs)


def _pass_rate(
    runs: Sequence[EvaluationRun],
    results_by_run: dict[str, CaseResult],
    evaluator_name: str,
) -> float:
    if not runs:
        return 0.0
    passed = 0
    for run in runs:
        if run.error is not None:
            continue  # failed provider run: counts in the denominator, not passed
        scores = {s.evaluator: s for s in results_by_run[run.id].scores}
        score = scores.get(evaluator_name)
        if score is None:
            raise ConfigError(
                f"successful run {run.id!r} is missing the {evaluator_name!r} evaluator score"
            )
        if score.passed:
            passed += 1
    return passed / len(runs)


def _successful_latencies(runs: Sequence[EvaluationRun]) -> list[float]:
    return [r.usage.latency_ms for r in runs if r.error is None]


def _latency_mean(runs: Sequence[EvaluationRun]) -> float:
    values = _successful_latencies(runs)
    return sum(values) / len(values) if values else 0.0


def _latency_p95(runs: Sequence[EvaluationRun]) -> float:
    values = sorted(_successful_latencies(runs))
    if not values:
        return 0.0
    rank = math.ceil(0.95 * len(values))
    return values[rank - 1]


def _cost_total(runs: Sequence[EvaluationRun]) -> float:
    return sum(r.usage.cost_usd for r in runs)


def _validate_outcome(
    experiment: Experiment,
    outcome: RunOutcome,
    evaluator_names: Sequence[str],
) -> None:
    runs, case_results = outcome.runs, outcome.case_results

    if len(runs) != len(case_results):
        raise ConfigError(f"RunOutcome has {len(runs)} runs but {len(case_results)} case results")
    run_ids = [r.id for r in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ConfigError("RunOutcome contains duplicate EvaluationRun ids")
    for index, (run, case_result) in enumerate(zip(runs, case_results, strict=True)):
        if case_result.run_id != run.id:
            raise ConfigError(
                f"RunOutcome misaligned at index {index}: "
                f"case_result.run_id {case_result.run_id!r} != run.id {run.id!r}"
            )

    names = list(evaluator_names)
    if len(names) != len(set(names)):
        raise ConfigError(f"evaluator_names contains duplicates: {sorted(names)}")
    required = set(names)
    valid_versions = {experiment.baseline_version_id, experiment.candidate_version_id}

    for run, case_result in zip(runs, case_results, strict=True):
        if run.experiment_id != experiment.id:
            raise ConfigError(
                f"run {run.id!r} has experiment_id {run.experiment_id!r}, "
                f"expected {experiment.id!r}"
            )
        if run.system_version_id not in valid_versions:
            raise ConfigError(
                f"run {run.id!r} has unexpected system_version_id {run.system_version_id!r}"
            )
        if run.error is None:
            missing = sorted(required - {s.evaluator for s in case_result.scores})
            if missing:
                raise ConfigError(
                    f"successful run {run.id!r} is missing evaluator score(s): {missing}"
                )
