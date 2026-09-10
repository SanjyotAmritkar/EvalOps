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
        evidence=[
            _metric_evidence_to_orm(evidence, position)
            for position, evidence in enumerate(value.evidence)
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
        evidence=tuple(_metric_evidence_from_orm(evidence) for evidence in row.evidence),
    )


def _metric_evidence_to_orm(value: domain.MetricEvidence, position: int) -> orm.MetricEvidence:
    return orm.MetricEvidence(
        metric=value.metric,
        position=position,
        kind=value.kind,
        n_pairs=value.n_pairs,
        baseline_mean=value.baseline.mean,
        baseline_median=value.baseline.median,
        baseline_stdev=value.baseline.stdev,
        candidate_mean=value.candidate.mean,
        candidate_median=value.candidate.median,
        candidate_stdev=value.candidate.stdev,
        paired_delta_mean=value.paired_delta.mean,
        paired_delta_median=value.paired_delta.median,
        paired_delta_stdev=value.paired_delta.stdev,
        delta=value.delta,
        relative_change=value.relative_change,
        confidence_level=value.confidence_level,
        ci_low=value.ci_low,
        ci_high=value.ci_high,
        ci_excludes_zero=value.ci_excludes_zero,
        insufficient_evidence=value.insufficient_evidence,
        dropped_provider_failures=value.dropped_provider_failures,
        method=value.method,
        resamples=value.resamples,
        seed=value.seed,
    )


def _metric_evidence_from_orm(row: orm.MetricEvidence) -> domain.MetricEvidence:
    def _summary(mean: float, median: float, stdev: float) -> domain.SampleSummary:
        return domain.SampleSummary(n=row.n_pairs, mean=mean, median=median, stdev=stdev)

    kind: domain.MetricKind = "binary" if row.kind == "binary" else "continuous"
    return domain.MetricEvidence(
        metric=row.metric,
        kind=kind,
        n_pairs=row.n_pairs,
        baseline=_summary(row.baseline_mean, row.baseline_median, row.baseline_stdev),
        candidate=_summary(row.candidate_mean, row.candidate_median, row.candidate_stdev),
        paired_delta=_summary(
            row.paired_delta_mean, row.paired_delta_median, row.paired_delta_stdev
        ),
        delta=row.delta,
        relative_change=row.relative_change,
        confidence_level=row.confidence_level,
        ci_low=row.ci_low,
        ci_high=row.ci_high,
        ci_excludes_zero=row.ci_excludes_zero,
        insufficient_evidence=row.insufficient_evidence,
        method=row.method,
        resamples=row.resamples,
        seed=row.seed,
        dropped_provider_failures=row.dropped_provider_failures,
    )


# --- AsyncJob -------------------------------------------------------


def async_job_to_orm(value: domain.AsyncJob) -> orm.AsyncJob:
    return orm.AsyncJob(
        id=value.id,
        experiment_id=value.experiment_id,
        status=value.status,
        celery_task_id=value.celery_task_id,
        evaluation_result_id=value.evaluation_result_id,
        error=value.error,
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
    )


def async_job_from_orm(row: orm.AsyncJob) -> domain.AsyncJob:
    return domain.AsyncJob(
        id=row.id,
        experiment_id=row.experiment_id,
        status=row.status,
        celery_task_id=row.celery_task_id,
        evaluation_result_id=row.evaluation_result_id,
        error=row.error,
        created_at=_aware(row.created_at),
        started_at=None if row.started_at is None else _aware(row.started_at),
        completed_at=None if row.completed_at is None else _aware(row.completed_at),
    )


# --- JudgeCalibration + JudgeCalibrationCase (Phase 6, CP 6.2) -------


def judge_calibration_to_orm(value: domain.JudgeCalibration) -> orm.JudgeCalibration:
    m = value.metrics
    return orm.JudgeCalibration(
        id=value.id,
        created_at=value.created_at,
        judge_provider=value.judge_provider,
        judge_model=value.judge_model,
        judge_name=value.judge_name,
        judge_temperature=value.judge_temperature,
        rubric_id=value.rubric_id,
        total=m.total,
        scored=m.scored,
        failures=m.failures,
        agreements=m.agreements,
        agreement_rate=m.agreement_rate,
        true_positives=m.true_positives,
        true_negatives=m.true_negatives,
        false_positives=m.false_positives,
        false_negatives=m.false_negatives,
        precision=m.precision,
        recall=m.recall,
        f1=m.f1,
        cases=[
            orm.JudgeCalibrationCase(
                position=position,
                input=case.input,
                output=case.output,
                reference=case.reference,
                human_pass=case.human_pass,
                judge_pass=case.judge_pass,
                judge_score=case.judge_score,
                judge_reasoning=case.judge_reasoning,
                error=case.error,
            )
            for position, case in enumerate(value.cases)
        ],
    )


def judge_calibration_from_orm(row: orm.JudgeCalibration) -> domain.JudgeCalibration:
    return domain.JudgeCalibration(
        id=row.id,
        created_at=_aware(row.created_at),
        judge_provider=row.judge_provider,
        judge_model=row.judge_model,
        judge_name=row.judge_name,
        judge_temperature=row.judge_temperature,
        rubric_id=row.rubric_id,
        metrics=domain.JudgeCalibrationMetrics(
            total=row.total,
            scored=row.scored,
            failures=row.failures,
            agreements=row.agreements,
            agreement_rate=row.agreement_rate,
            true_positives=row.true_positives,
            true_negatives=row.true_negatives,
            false_positives=row.false_positives,
            false_negatives=row.false_negatives,
            precision=row.precision,
            recall=row.recall,
            f1=row.f1,
        ),
        cases=tuple(
            domain.JudgeCalibrationCase(
                input=case.input,
                output=case.output,
                reference=case.reference,
                human_pass=case.human_pass,
                judge_pass=case.judge_pass,
                judge_score=case.judge_score,
                judge_reasoning=case.judge_reasoning,
                error=case.error,
            )
            for case in row.cases
        ),
    )


# --- ProductionTrace (Phase 8, CP 8.1) -----------------------------


def production_trace_to_orm(value: domain.ProductionTrace) -> orm.ProductionTrace:
    return orm.ProductionTrace(
        id=value.id,
        project_id=value.project_id,
        system_version_id=value.system_version_id,
        created_at=value.created_at,
        input=value.input,
        output=value.output,
        reference_output=value.reference_output,
        trace_metadata=dict(value.metadata),
        latency_ms=value.latency_ms,
        cost_usd=value.cost_usd,
        error=value.error,
        origin=value.origin,
    )


def production_trace_from_orm(row: orm.ProductionTrace) -> domain.ProductionTrace:
    return domain.ProductionTrace(
        id=row.id,
        project_id=row.project_id,
        system_version_id=row.system_version_id,
        created_at=_aware(row.created_at),
        input=row.input,
        output=row.output,
        reference_output=row.reference_output,
        metadata=row.trace_metadata,
        latency_ms=row.latency_ms,
        cost_usd=row.cost_usd,
        error=row.error,
        origin=row.origin,
    )
