"""Explicit conversions between frozen domain objects and ORM rows.

The domain dataclasses (:mod:`evalops.domain`) and the ORM models
(:mod:`evalops.db.models`) stay separate; this module is the only place they
meet. Ids, timestamps, ordering, enums, JSON/map fields, usage metrics,
evaluator scores, and metric comparisons all round-trip.
"""

from __future__ import annotations

from datetime import UTC, datetime

from evalops import domain
from evalops.db import models as orm


def _aware(value: datetime) -> datetime:
    """Backends without native tz storage (SQLite) return naive datetimes; the
    domain stores UTC, so re-attach it."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Project ---------------------------------------------------------------


def project_to_orm(value: domain.Project) -> orm.Project:
    return orm.Project(id=value.id, name=value.name, created_at=value.created_at)


def project_from_orm(row: orm.Project) -> domain.Project:
    return domain.Project(id=row.id, name=row.name, created_at=_aware(row.created_at))


# --- Dataset + DatasetCase ----------------------------------------------


def dataset_to_orm(value: domain.Dataset) -> orm.Dataset:
    return orm.Dataset(
        id=value.id,
        project_id=value.project_id,
        name=value.name,
        version=value.version,
        created_at=value.created_at,
        cases=[_case_to_orm(case, position) for position, case in enumerate(value.cases)],
    )


def dataset_from_orm(row: orm.Dataset) -> domain.Dataset:
    return domain.Dataset(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        version=row.version,
        created_at=_aware(row.created_at),
        cases=tuple(_case_from_orm(case) for case in row.cases),
    )


def _case_to_orm(value: domain.DatasetCase, position: int) -> orm.DatasetCase:
    return orm.DatasetCase(
        id=value.id,
        position=position,
        input=value.input,
        expected_output=value.expected_output,
        origin=value.origin,
        source_trace_id=value.source_trace_id,
    )


def _case_from_orm(row: orm.DatasetCase) -> domain.DatasetCase:
    return domain.DatasetCase(
        id=row.id,
        input=row.input,
        expected_output=row.expected_output,
        origin=row.origin,
        source_trace_id=row.source_trace_id,
    )


# --- SystemVersion ------------------------------------------------------


def system_version_to_orm(value: domain.SystemVersion) -> orm.SystemVersion:
    return orm.SystemVersion(
        id=value.id,
        project_id=value.project_id,
        name=value.name,
        version=value.version,
        provider=value.provider,
        model=value.model,
        prompt_template=value.prompt_template,
        parameters=dict(value.parameters),
        rag_config=None if value.rag_config is None else dict(value.rag_config),
        tool_policy=None if value.tool_policy is None else dict(value.tool_policy),
        created_at=value.created_at,
    )


def system_version_from_orm(row: orm.SystemVersion) -> domain.SystemVersion:
    return domain.SystemVersion(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        version=row.version,
        provider=row.provider,
        model=row.model,
        prompt_template=row.prompt_template,
        parameters=row.parameters,
        rag_config=row.rag_config,
        tool_policy=row.tool_policy,
        created_at=_aware(row.created_at),
    )


# --- ReleasePolicy ----------------------------------------------------


def release_policy_to_orm(value: domain.ReleasePolicy) -> orm.ReleasePolicy:
    return orm.ReleasePolicy(
        id=value.id,
        name=value.name,
        thresholds=dict(value.thresholds),
        max_safety_violations=value.max_safety_violations,
    )


def release_policy_from_orm(row: orm.ReleasePolicy) -> domain.ReleasePolicy:
    return domain.ReleasePolicy(
        id=row.id,
        name=row.name,
        thresholds=row.thresholds,
        max_safety_violations=row.max_safety_violations,
    )


# --- Experiment -----------------------------------------------------


def experiment_to_orm(value: domain.Experiment) -> orm.Experiment:
    return orm.Experiment(
        id=value.id,
        project_id=value.project_id,
        dataset_id=value.dataset_id,
        baseline_version_id=value.baseline_version_id,
        candidate_version_id=value.candidate_version_id,
        release_policy_id=value.release_policy_id,
        repeats=value.repeats,
        created_at=value.created_at,
    )


def experiment_from_orm(row: orm.Experiment) -> domain.Experiment:
    return domain.Experiment(
        id=row.id,
        project_id=row.project_id,
        dataset_id=row.dataset_id,
        baseline_version_id=row.baseline_version_id,
        candidate_version_id=row.candidate_version_id,
        release_policy_id=row.release_policy_id,
        repeats=row.repeats,
        created_at=_aware(row.created_at),
    )


# --- EvaluationRun (flattens UsageMetrics) ---------------------------


def evaluation_run_to_orm(value: domain.EvaluationRun) -> orm.EvaluationRun:
    return orm.EvaluationRun(
        id=value.id,
        experiment_id=value.experiment_id,
        system_version_id=value.system_version_id,
        case_id=value.case_id,
        repeat_index=value.repeat_index,
        output=value.output,
        error=value.error,
        prompt_tokens=value.usage.prompt_tokens,
        completion_tokens=value.usage.completion_tokens,
        cost_usd=value.usage.cost_usd,
        latency_ms=value.usage.latency_ms,
        created_at=value.created_at,
    )


def evaluation_run_from_orm(row: orm.EvaluationRun) -> domain.EvaluationRun:
    return domain.EvaluationRun(
        id=row.id,
        experiment_id=row.experiment_id,
        system_version_id=row.system_version_id,
        case_id=row.case_id,
        repeat_index=row.repeat_index,
        output=row.output,
        error=row.error,
        usage=domain.UsageMetrics(
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            cost_usd=row.cost_usd,
            latency_ms=row.latency_ms,
        ),
        created_at=_aware(row.created_at),
    )


# --- CaseResult + EvaluatorScore ----------------------------------


def case_result_to_orm(value: domain.CaseResult) -> orm.CaseResult:
    return orm.CaseResult(
        id=value.id,
        run_id=value.run_id,
        created_at=value.created_at,
        scores=[
            orm.EvaluatorScore(
                evaluator=score.evaluator,
                position=position,
                family=score.family,
                score=score.score,
                passed=score.passed,
            )
            for position, score in enumerate(value.scores)
        ],
    )


def case_result_from_orm(row: orm.CaseResult) -> domain.CaseResult:
    return domain.CaseResult(
        id=row.id,
        run_id=row.run_id,
        created_at=_aware(row.created_at),
        scores=tuple(
            domain.EvaluatorScore(
                evaluator=score.evaluator,
                family=score.family,
                score=score.score,
                passed=score.passed,
            )
            for score in row.scores
        ),
    )


# --- EvaluationResult + MetricComparison ------------------------


def evaluation_result_to_orm(value: domain.EvaluationResult) -> orm.EvaluationResult:
    return orm.EvaluationResult(
        id=value.id,
        experiment_id=value.experiment_id,
        created_at=value.created_at,
        metrics=[
            orm.MetricComparison(
                metric=metric.metric,
                position=position,
                baseline_value=metric.baseline_value,
                candidate_value=metric.candidate_value,
            )
            for position, metric in enumerate(value.metrics)
        ],
    )


def evaluation_result_from_orm(row: orm.EvaluationResult) -> domain.EvaluationResult:
    return domain.EvaluationResult(
        id=row.id,
        experiment_id=row.experiment_id,
        created_at=_aware(row.created_at),
        metrics=tuple(
            domain.MetricComparison(
                metric=metric.metric,
                baseline_value=metric.baseline_value,
                candidate_value=metric.candidate_value,
            )
            for metric in row.metrics
        ),
    )
