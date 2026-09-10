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
    ProductionTrace,
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
    TraceOrigin,
)
from evalops.domain.errors import DomainValidationError, EvalOpsError
from evalops.domain.ids import EntityId, new_id
from evalops.domain.value_objects import (
    EvaluatorScore,
    ExpectedToolCall,
    JudgeCalibrationCase,
    JudgeCalibrationMetrics,
    LabeledJudgeExample,
    MetricComparison,
    MetricEvidence,
    MetricKind,
    RetrievedItem,
    SampleSummary,
    ToolCall,
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
    "ExpectedToolCall",
    "Experiment",
    "JobStatus",
    "JudgeCalibration",
    "JudgeCalibrationCase",
    "JudgeCalibrationMetrics",
    "LabeledJudgeExample",
    "MetricComparison",
    "MetricEvidence",
    "MetricKind",
    "ProductionTrace",
    "Project",
    "ProviderClient",
    "ProviderError",
    "ProviderName",
    "ProviderResponse",
    "ReleaseDecision",
    "ReleasePolicy",
    "RetrievedItem",
    "SampleSummary",
    "SystemVersion",
    "ToolCall",
    "TraceOrigin",
    "UsageMetrics",
    "new_id",
]
