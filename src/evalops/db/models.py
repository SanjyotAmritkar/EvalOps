"""SQLAlchemy ORM models mirroring the frozen Phase 0 domain entities.

These tables persist the same concepts as :mod:`evalops.domain` -- ids,
versions, provider/model/config, prompts, timestamps, usage metrics, errors,
evaluator scores, and release-policy thresholds -- without redefining the
domain. Value objects that the domain embeds (``UsageMetrics``,
``EvaluatorScore``, ``MetricComparison``) become flat columns or child rows.
No business logic lives here.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evalops.db.base import ID_LENGTH, Base, JSONMap
from evalops.domain.enums import CaseOrigin, EvaluatorFamily, JobStatus, ProviderName


def _enum(py_enum: type[enum.Enum], name: str) -> Enum:
    """A VARCHAR + CHECK column storing the enum's wire value (not its name)."""
    return Enum(
        py_enum,
        native_enum=False,
        values_callable=lambda members: [str(m.value) for m in members],
        name=name,
    )


def _id_column() -> Mapped[str]:
    return mapped_column(String(ID_LENGTH), primary_key=True)


def _fk(target: str, *, nullable: bool = False, index: bool = True) -> Mapped[str]:
    return mapped_column(
        String(ID_LENGTH), ForeignKey(target, ondelete="CASCADE"), nullable=nullable, index=index
    )


class Project(Base):
    __tablename__ = "project"

    id: Mapped[str] = _id_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    system_versions: Mapped[list[SystemVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    experiments: Mapped[list[Experiment]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Dataset(Base):
    __tablename__ = "dataset"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[str] = _id_column()
    project_id: Mapped[str] = _fk("project.id")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped[Project] = relationship(back_populates="datasets")
    cases: Mapped[list[DatasetCase]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetCase.position",
        passive_deletes=True,
    )


class DatasetCase(Base):
    __tablename__ = "dataset_case"
    __table_args__ = (
        UniqueConstraint("dataset_id", "position"),
        CheckConstraint(
            "(origin = 'promoted_trace') = (source_trace_id IS NOT NULL)",
            name="trace_id_iff_promoted",
        ),
    )

    id: Mapped[str] = _id_column()
    dataset_id: Mapped[str] = _fk("dataset.id")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[CaseOrigin] = mapped_column(
        _enum(CaseOrigin, "case_origin"), nullable=False, default=CaseOrigin.AUTHORED
    )
    source_trace_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="cases")


class SystemVersion(Base):
    __tablename__ = "system_version"
    __table_args__ = (UniqueConstraint("project_id", "name", "version"),)

    id: Mapped[str] = _id_column()
    project_id: Mapped[str] = _fk("project.id")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[ProviderName] = mapped_column(
        _enum(ProviderName, "provider_name"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONMap, nullable=False, default=dict)
    rag_config: Mapped[dict[str, Any] | None] = mapped_column(JSONMap, nullable=True)
    tool_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONMap, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped[Project] = relationship(back_populates="system_versions")


class ReleasePolicy(Base):
    __tablename__ = "release_policy"
    __table_args__ = (
        CheckConstraint("max_safety_violations >= 0", name="max_safety_violations_nonneg"),
    )

    id: Mapped[str] = _id_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONMap, nullable=False, default=dict)
    max_safety_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Experiment(Base):
    __tablename__ = "experiment"
    __table_args__ = (
        CheckConstraint("repeats >= 1", name="repeats_positive"),
        CheckConstraint(
            "baseline_version_id <> candidate_version_id", name="baseline_ne_candidate"
        ),
    )

    id: Mapped[str] = _id_column()
    project_id: Mapped[str] = _fk("project.id")
    dataset_id: Mapped[str] = _fk("dataset.id")
    baseline_version_id: Mapped[str] = _fk("system_version.id")
    candidate_version_id: Mapped[str] = _fk("system_version.id")
    release_policy_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("release_policy.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    repeats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped[Project] = relationship(back_populates="experiments")
    dataset: Mapped[Dataset] = relationship()
    baseline_version: Mapped[SystemVersion] = relationship(foreign_keys=[baseline_version_id])
    candidate_version: Mapped[SystemVersion] = relationship(foreign_keys=[candidate_version_id])
    release_policy: Mapped[ReleasePolicy | None] = relationship()
    evaluation_runs: Mapped[list[EvaluationRun]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True
    )
    evaluation_results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", passive_deletes=True
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_run"
    __table_args__ = (
        UniqueConstraint("experiment_id", "system_version_id", "case_id", "repeat_index"),
        CheckConstraint("repeat_index >= 0", name="repeat_index_nonneg"),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND cost_usd >= 0 AND latency_ms >= 0",
            name="usage_nonneg",
        ),
    )

    id: Mapped[str] = _id_column()
    experiment_id: Mapped[str] = _fk("experiment.id")
    system_version_id: Mapped[str] = _fk("system_version.id")
    case_id: Mapped[str] = _fk("dataset_case.id")
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="evaluation_runs")
    case_result: Mapped[CaseResult | None] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False, passive_deletes=True
    )


class CaseResult(Base):
    __tablename__ = "case_result"
    __table_args__ = (UniqueConstraint("run_id"),)

    id: Mapped[str] = _id_column()
    run_id: Mapped[str] = _fk("evaluation_run.id")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[EvaluationRun] = relationship(back_populates="case_result")
    scores: Mapped[list[EvaluatorScore]] = relationship(
        back_populates="case_result",
        cascade="all, delete-orphan",
        order_by="EvaluatorScore.position",
        passive_deletes=True,
    )


class EvaluatorScore(Base):
    __tablename__ = "evaluator_score"
    __table_args__ = (
        UniqueConstraint("case_result_id", "position"),
        CheckConstraint("score >= 0.0 AND score <= 1.0", name="score_unit_interval"),
    )

    case_result_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("case_result.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    evaluator: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    family: Mapped[EvaluatorFamily] = mapped_column(
        _enum(EvaluatorFamily, "evaluator_family"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool | None] = mapped_column(nullable=True)

    case_result: Mapped[CaseResult] = relationship(back_populates="scores")


class EvaluationResult(Base):
    __tablename__ = "evaluation_result"

    id: Mapped[str] = _id_column()
    experiment_id: Mapped[str] = _fk("experiment.id")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="evaluation_results")
    metrics: Mapped[list[MetricComparison]] = relationship(
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
        order_by="MetricComparison.position",
        passive_deletes=True,
    )
    evidence: Mapped[list[MetricEvidence]] = relationship(
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
        order_by="MetricEvidence.position",
        passive_deletes=True,
    )


class AsyncJob(Base):
    """Durable lifecycle of a background experiment run (queued -> running ->
    completed | failed). Not an evaluation-domain concept -- execution state
    that outlives Celery/Redis so PostgreSQL stays authoritative."""

    __tablename__ = "async_job"

    id: Mapped[str] = _id_column()
    experiment_id: Mapped[str] = _fk("experiment.id")
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evaluation_result_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("evaluation_result.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    experiment: Mapped[Experiment] = relationship()


class MetricComparison(Base):
    __tablename__ = "metric_comparison"
    __table_args__ = (UniqueConstraint("evaluation_result_id", "position"),)

    evaluation_result_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("evaluation_result.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_value: Mapped[float] = mapped_column(Float, nullable=False)

    evaluation_result: Mapped[EvaluationResult] = relationship(back_populates="metrics")


class MetricEvidence(Base):
    """Per-metric paired-bootstrap statistical evidence for an EvaluationResult
    (Phase 5). Flat columns, like ``metric_comparison`` -- the three
    ``SampleSummary`` value objects (baseline / candidate / paired-delta) are
    flattened onto ``*_mean`` / ``*_median`` / ``*_stdev``; their ``n`` is
    always ``n_pairs``."""

    __tablename__ = "metric_evidence"
    __table_args__ = (
        UniqueConstraint("evaluation_result_id", "position"),
        CheckConstraint("kind IN ('binary', 'continuous')", name="kind_known"),
        CheckConstraint("n_pairs >= 0", name="n_pairs_nonneg"),
        CheckConstraint("dropped_provider_failures >= 0", name="dropped_nonneg"),
        CheckConstraint(
            "confidence_level > 0.0 AND confidence_level < 1.0", name="confidence_level_unit"
        ),
    )

    evaluation_result_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("evaluation_result.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    n_pairs: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_mean: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_median: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_stdev: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_mean: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_median: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_stdev: Mapped[float] = mapped_column(Float, nullable=False)
    paired_delta_mean: Mapped[float] = mapped_column(Float, nullable=False)
    paired_delta_median: Mapped[float] = mapped_column(Float, nullable=False)
    paired_delta_stdev: Mapped[float] = mapped_column(Float, nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    relative_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_excludes_zero: Mapped[bool] = mapped_column(nullable=False)
    insufficient_evidence: Mapped[bool] = mapped_column(nullable=False)
    dropped_provider_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    resamples: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)

    evaluation_result: Mapped[EvaluationResult] = relationship(back_populates="evidence")


class JudgeCalibration(Base):
    """A run of one configured LLM judge against a human-labeled set (Phase 6,
    CP 6.2). Judge identity + config metadata and the aggregate agreement
    metrics are flat columns; per-example detail lives in
    ``judge_calibration_case``. Standalone -- no experiment/project FK, since
    calibration is separate from release gating. Never stores credentials."""

    __tablename__ = "judge_calibration"
    __table_args__ = (
        CheckConstraint("judge_temperature >= 0.0", name="judge_temperature_nonneg"),
        CheckConstraint("total >= 0 AND scored >= 0 AND failures >= 0", name="counts_nonneg"),
    )

    id: Mapped[str] = _id_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    judge_provider: Mapped[ProviderName] = mapped_column(
        _enum(ProviderName, "provider_name"), nullable=False
    )
    judge_model: Mapped[str] = mapped_column(String(200), nullable=False)
    judge_name: Mapped[str] = mapped_column(String(200), nullable=False)
    judge_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    rubric_id: Mapped[str] = mapped_column(String(64), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    scored: Mapped[int] = mapped_column(Integer, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, nullable=False)
    agreements: Mapped[int] = mapped_column(Integer, nullable=False)
    agreement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    true_positives: Mapped[int] = mapped_column(Integer, nullable=False)
    true_negatives: Mapped[int] = mapped_column(Integer, nullable=False)
    false_positives: Mapped[int] = mapped_column(Integer, nullable=False)
    false_negatives: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1: Mapped[float | None] = mapped_column(Float, nullable=True)

    cases: Mapped[list[JudgeCalibrationCase]] = relationship(
        back_populates="calibration",
        cascade="all, delete-orphan",
        order_by="JudgeCalibrationCase.position",
        passive_deletes=True,
    )


class JudgeCalibrationCase(Base):
    __tablename__ = "judge_calibration_case"
    __table_args__ = (
        CheckConstraint(
            "(judge_pass IS NULL) = (error IS NOT NULL)", name="error_iff_judge_failed"
        ),
    )

    calibration_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("judge_calibration.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_pass: Mapped[bool] = mapped_column(nullable=False)
    judge_pass: Mapped[bool | None] = mapped_column(nullable=True)
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    calibration: Mapped[JudgeCalibration] = relationship(back_populates="cases")
