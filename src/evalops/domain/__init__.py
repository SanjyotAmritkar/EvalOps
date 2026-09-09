"""EvalOps domain model.

Framework-independent entities, value objects, and contracts, frozen in Phase 0.
See docs/ARCHITECTURE.md sections 6 to 8.
"""

from evalops.domain.contracts import (
    Evaluator,
    ProviderClient,
    ProviderError,
    ProviderResponse,
)
from evalops.domain.entities import (
    AsyncJob,
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationResult,
    EvaluationRun,
    Experiment,
    JudgeCalibration,
    Project,
    ReleasePolicy,
    SystemVersion,
)
from evalops.domain.enums import (
    CaseOrigin,
    EvaluatorFamily,
    JobStatus,
    ProviderName,
    ReleaseDecision,
)
from evalops.domain.errors import DomainValidationError, EvalOpsError
from evalops.domain.ids import EntityId, new_id
from evalops.domain.value_objects import (
    EvaluatorScore,
    JudgeCalibrationCase,
    JudgeCalibrationMetrics,
    LabeledJudgeExample,
    MetricComparison,
    MetricEvidence,
    MetricKind,
    SampleSummary,
    UsageMetrics,
)

__all__ = [
    "AsyncJob",
    "CaseOrigin",
    "CaseResult",
    "Dataset",
    "DatasetCase",
    "DomainValidationError",
    "EntityId",
    "EvalOpsError",
    "EvaluationResult",
    "EvaluationRun",
    "Evaluator",
    "EvaluatorFamily",
    "EvaluatorScore",
    "Experiment",
    "JobStatus",
    "JudgeCalibration",
    "JudgeCalibrationCase",
    "JudgeCalibrationMetrics",
    "LabeledJudgeExample",
    "MetricComparison",
    "MetricEvidence",
    "MetricKind",
    "Project",
    "ProviderClient",
    "ProviderError",
    "ProviderName",
    "ProviderResponse",
    "ReleaseDecision",
    "ReleasePolicy",
    "SampleSummary",
    "SystemVersion",
    "UsageMetrics",
    "new_id",
]
