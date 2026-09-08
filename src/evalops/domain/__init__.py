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
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationResult,
    EvaluationRun,
    Experiment,
    Project,
    ReleasePolicy,
    SystemVersion,
)
from evalops.domain.enums import CaseOrigin, EvaluatorFamily, ProviderName, ReleaseDecision
from evalops.domain.errors import DomainValidationError, EvalOpsError
from evalops.domain.ids import EntityId, new_id
from evalops.domain.value_objects import EvaluatorScore, MetricComparison, UsageMetrics

__all__ = [
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
    "MetricComparison",
    "Project",
    "ProviderClient",
    "ProviderError",
    "ProviderName",
    "ProviderResponse",
    "ReleaseDecision",
    "ReleasePolicy",
    "SystemVersion",
    "UsageMetrics",
    "new_id",
]
