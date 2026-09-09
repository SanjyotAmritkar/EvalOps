"""Core domain entities: Project, SystemVersion, DatasetCase, Dataset.

Frozen dataclasses that validate their invariants on construction. See
docs/ARCHITECTURE.md section 6. Entities reference each other by string id;
a Dataset embeds its DatasetCases as an immutable tuple.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from evalops.domain._time import utcnow
from evalops.domain.enums import CaseOrigin, JobStatus, ProviderName
from evalops.domain.errors import DomainValidationError
from evalops.domain.ids import new_id
from evalops.domain.value_objects import (
    EvaluatorScore,
    JudgeCalibrationCase,
    JudgeCalibrationMetrics,
    MetricComparison,
    MetricEvidence,
    UsageMetrics,
)


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{label} must be a non-empty string")


def _require_aware(moment: datetime, label: str) -> None:
    if moment.tzinfo is None:
        raise DomainValidationError(f"{label} must be a timezone-aware datetime")


def _read_only(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a shallow-immutable view over a private copy of ``mapping``.

    The top level cannot be mutated (no add/remove/rebind of keys). Nested
    mutable values are left as-is; this is not a deep freeze.
    """
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, slots=True)
class Project:
    """Top-level container for one system under evaluation."""

    name: str
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "Project.name")
        _require_non_empty(self.id, "Project.id")
        _require_aware(self.created_at, "Project.created_at")


@dataclass(frozen=True, slots=True)
class SystemVersion:
    """A named, versioned, immutable configuration of a system under evaluation.

    This is the reproducibility anchor: re-running an experiment must reproduce
    exactly this configuration. ``rag_config`` and ``tool_policy`` are opaque in
    the current phase and carry no behavior.

    ``parameters``, ``rag_config`` and ``tool_policy`` are stored as read-only
    mappings: their top level cannot be mutated after construction. Nested
    mutable values (e.g. a list inside ``parameters``) are intentionally left
    mutable -- this is a shallow guarantee, not a deep freeze.
    """

    project_id: str
    name: str
    version: str
    provider: ProviderName
    model: str
    prompt_template: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    rag_config: Mapping[str, Any] | None = None
    tool_policy: Mapping[str, Any] | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ProviderName):
            raise DomainValidationError(
                "SystemVersion.provider must be a ProviderName member, "
                f"got {type(self.provider).__name__}"
            )
        for value, label in (
            (self.project_id, "SystemVersion.project_id"),
            (self.name, "SystemVersion.name"),
            (self.version, "SystemVersion.version"),
            (self.model, "SystemVersion.model"),
            (self.prompt_template, "SystemVersion.prompt_template"),
            (self.id, "SystemVersion.id"),
        ):
            _require_non_empty(value, label)
        _require_aware(self.created_at, "SystemVersion.created_at")
        # Store config maps as read-only proxies over private copies, so neither
        # the caller's original dict nor the field itself can mutate the stored
        # configuration (shallow; see class docstring).
        object.__setattr__(self, "parameters", _read_only(self.parameters))
        if self.rag_config is not None:
            object.__setattr__(self, "rag_config", _read_only(self.rag_config))
        if self.tool_policy is not None:
            object.__setattr__(self, "tool_policy", _read_only(self.tool_policy))


@dataclass(frozen=True, slots=True)
class DatasetCase:
    """A single evaluation case: an input and, optionally, a reference output."""

    input: str
    expected_output: str | None = None
    origin: CaseOrigin = CaseOrigin.AUTHORED
    source_trace_id: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        _require_non_empty(self.input, "DatasetCase.input")
        _require_non_empty(self.id, "DatasetCase.id")
        has_trace = bool(self.source_trace_id and self.source_trace_id.strip())
        if self.origin is CaseOrigin.PROMOTED_TRACE and not has_trace:
            raise DomainValidationError(
                "DatasetCase.source_trace_id is required when origin is promoted_trace"
            )
        if self.origin is CaseOrigin.AUTHORED and self.source_trace_id is not None:
            raise DomainValidationError(
                "DatasetCase.source_trace_id must be unset when origin is authored"
            )


@dataclass(frozen=True, slots=True)
class Dataset:
    """A versioned, immutable collection of DatasetCases."""

    project_id: str
    name: str
    version: int
    cases: tuple[DatasetCase, ...]
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.project_id, "Dataset.project_id")
        _require_non_empty(self.name, "Dataset.name")
        _require_non_empty(self.id, "Dataset.id")
        _require_aware(self.created_at, "Dataset.created_at")
        if self.version < 1:
            raise DomainValidationError(f"Dataset.version must be >= 1, got {self.version}")
        object.__setattr__(self, "cases", tuple(self.cases))
        if not self.cases:
            raise DomainValidationError("Dataset.cases must not be empty")
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise DomainValidationError("Dataset.cases contains duplicate case ids")


@dataclass(frozen=True, slots=True)
class Experiment:
    """A defined comparison of a baseline SystemVersion against a candidate one
    over a Dataset. Execution state is not modelled in this phase.
    """

    project_id: str
    dataset_id: str
    baseline_version_id: str
    candidate_version_id: str
    repeats: int = 1
    release_policy_id: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        for value, label in (
            (self.project_id, "Experiment.project_id"),
            (self.dataset_id, "Experiment.dataset_id"),
            (self.baseline_version_id, "Experiment.baseline_version_id"),
            (self.candidate_version_id, "Experiment.candidate_version_id"),
            (self.id, "Experiment.id"),
        ):
            _require_non_empty(value, label)
        if self.baseline_version_id == self.candidate_version_id:
            raise DomainValidationError(
                "Experiment baseline and candidate must be different SystemVersions"
            )
        if self.repeats < 1:
            raise DomainValidationError(f"Experiment.repeats must be >= 1, got {self.repeats}")
        if self.release_policy_id is not None:
            _require_non_empty(self.release_policy_id, "Experiment.release_policy_id")
        _require_aware(self.created_at, "Experiment.created_at")


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    """One execution of one DatasetCase against one SystemVersion.

    A successful run carries the model ``output``; a failed run carries a
    non-blank ``error`` and typically an empty ``output`` with zero usage.
    """

    experiment_id: str
    system_version_id: str
    case_id: str
    repeat_index: int
    output: str
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    error: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        for value, label in (
            (self.experiment_id, "EvaluationRun.experiment_id"),
            (self.system_version_id, "EvaluationRun.system_version_id"),
            (self.case_id, "EvaluationRun.case_id"),
            (self.id, "EvaluationRun.id"),
        ):
            _require_non_empty(value, label)
        if self.repeat_index < 0:
            raise DomainValidationError(
                f"EvaluationRun.repeat_index must be >= 0, got {self.repeat_index}"
            )
        if self.error is not None and not self.error.strip():
            raise DomainValidationError("EvaluationRun.error must be non-blank when set")
        _require_aware(self.created_at, "EvaluationRun.created_at")


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The scored outcome of one EvaluationRun: its per-evaluator scores."""

    run_id: str
    scores: tuple[EvaluatorScore, ...]
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "CaseResult.run_id")
        _require_non_empty(self.id, "CaseResult.id")
        _require_aware(self.created_at, "CaseResult.created_at")
        object.__setattr__(self, "scores", tuple(self.scores))
        names = [score.evaluator for score in self.scores]
        if len(names) != len(set(names)):
            raise DomainValidationError("CaseResult.scores has duplicate evaluator names")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Experiment-level comparison: one MetricComparison per named metric, plus
    optional per-metric statistical ``evidence`` (Phase 5).

    Representation only. Aggregation from CaseResults, the statistical evidence,
    and any release decision are produced by later phases, not computed here.
    ``evidence`` defaults to empty so pre-Phase-5 results stay valid.
    """

    experiment_id: str
    metrics: tuple[MetricComparison, ...]
    evidence: tuple[MetricEvidence, ...] = ()
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "EvaluationResult.experiment_id")
        _require_non_empty(self.id, "EvaluationResult.id")
        _require_aware(self.created_at, "EvaluationResult.created_at")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        names = [comparison.metric for comparison in self.metrics]
        if len(names) != len(set(names)):
            raise DomainValidationError("EvaluationResult.metrics has duplicate metric names")
        evidence_metrics = [e.metric for e in self.evidence]
        if len(evidence_metrics) != len(set(evidence_metrics)):
            raise DomainValidationError("EvaluationResult.evidence has duplicate metric names")


@dataclass(frozen=True, slots=True)
class ReleasePolicy:
    """Release-gate thresholds. Representation only; no gating logic here.

    ``thresholds`` maps a metric name to the maximum tolerated adverse change
    for that metric, as a fraction (``0.15`` == 15%). Whether a change counts as
    adverse (higher-is-better vs lower-is-better) is a property of the metric,
    resolved by the gate engine in a later phase, not by this policy.
    """

    name: str
    thresholds: Mapping[str, float] = field(default_factory=dict)
    max_safety_violations: int = 0
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "ReleasePolicy.name")
        _require_non_empty(self.id, "ReleasePolicy.id")
        if self.max_safety_violations < 0:
            raise DomainValidationError(
                f"ReleasePolicy.max_safety_violations must be >= 0, "
                f"got {self.max_safety_violations}"
            )
        for metric, ceiling in self.thresholds.items():
            if not metric.strip():
                raise DomainValidationError("ReleasePolicy.thresholds has a blank metric name")
            if ceiling < 0:
                raise DomainValidationError(
                    f"ReleasePolicy threshold for {metric!r} must be >= 0, got {ceiling}"
                )
        object.__setattr__(self, "thresholds", _read_only(self.thresholds))


@dataclass(frozen=True, slots=True)
class AsyncJob:
    """A durable record of one background (async) experiment run.

    An immutable snapshot: lifecycle transitions are performed by the
    repository as targeted updates, each returning a fresh ``AsyncJob``.
    Invariants tie the ``status`` to which timestamp / error / result fields
    are set.
    """

    experiment_id: str
    status: JobStatus = JobStatus.QUEUED
    celery_task_id: str | None = None
    evaluation_result_id: str | None = None
    error: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.experiment_id, "AsyncJob.experiment_id")
        _require_non_empty(self.id, "AsyncJob.id")
        _require_aware(self.created_at, "AsyncJob.created_at")
        for moment, label in (
            (self.started_at, "AsyncJob.started_at"),
            (self.completed_at, "AsyncJob.completed_at"),
        ):
            if moment is not None:
                _require_aware(moment, label)
        if self.started_at is not None and self.started_at < self.created_at:
            raise DomainValidationError("AsyncJob.started_at is before created_at")
        if (
            self.completed_at is not None
            and self.started_at is not None
            and self.completed_at < self.started_at
        ):
            raise DomainValidationError("AsyncJob.completed_at is before started_at")
        if self.error is not None and not self.error.strip():
            raise DomainValidationError("AsyncJob.error must be non-blank when set")

        if self.status is JobStatus.QUEUED:
            if any((self.started_at, self.completed_at, self.error, self.evaluation_result_id)):
                raise DomainValidationError(
                    "a queued AsyncJob has no start/completion/error/result"
                )
        elif self.status is JobStatus.RUNNING:
            if self.started_at is None:
                raise DomainValidationError("a running AsyncJob has started_at")
            if any((self.completed_at, self.error, self.evaluation_result_id)):
                raise DomainValidationError("a running AsyncJob has no completion/error/result")
        elif self.status is JobStatus.COMPLETED:
            if (
                self.started_at is None
                or self.completed_at is None
                or self.evaluation_result_id is None
            ):
                raise DomainValidationError(
                    "a completed AsyncJob has started_at, completed_at and evaluation_result_id"
                )
            if self.error is not None:
                raise DomainValidationError("a completed AsyncJob has no error")
        else:  # JobStatus.FAILED
            if self.completed_at is None or self.error is None:
                raise DomainValidationError(
                    "a failed AsyncJob has completed_at and an error message"
                )
            if self.evaluation_result_id is not None:
                raise DomainValidationError("a failed AsyncJob has no evaluation_result_id")


@dataclass(frozen=True, slots=True)
class JudgeCalibration:
    """Persisted result of calibrating one configured LLM judge against a
    human-labeled set (Phase 6, CP 6.2).

    Pure measurement of judge trustworthiness. It records the judge's identity
    (provider / model / name / temperature / rubric) and config metadata --
    never credentials -- plus the aggregate metrics and every scored case. It
    is deliberately unconnected to Experiment / ReleasePolicy: calibration does
    not change release gating.
    """

    judge_provider: ProviderName
    judge_model: str
    judge_name: str
    judge_temperature: float
    rubric_id: str
    metrics: JudgeCalibrationMetrics
    cases: tuple[JudgeCalibrationCase, ...]
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.judge_provider, ProviderName):
            raise DomainValidationError(
                "JudgeCalibration.judge_provider must be a ProviderName member"
            )
        for value, label in (
            (self.judge_model, "JudgeCalibration.judge_model"),
            (self.judge_name, "JudgeCalibration.judge_name"),
            (self.rubric_id, "JudgeCalibration.rubric_id"),
            (self.id, "JudgeCalibration.id"),
        ):
            if not value.strip():
                raise DomainValidationError(f"{label} must be a non-empty string")
        if self.judge_temperature < 0:
            raise DomainValidationError("JudgeCalibration.judge_temperature must be >= 0")
        _require_aware(self.created_at, "JudgeCalibration.created_at")
        object.__setattr__(self, "cases", tuple(self.cases))
        if self.metrics.total != len(self.cases):
            raise DomainValidationError(
                "JudgeCalibration.metrics.total must equal the number of cases"
            )
