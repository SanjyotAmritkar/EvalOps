"""EvalOps domain model.

Framework-independent entities, value objects, and contracts, frozen in Phase 0.
See docs/ARCHITECTURE.md sections 6 to 8.
"""

from evalops.domain.enums import CaseOrigin, EvaluatorFamily, ProviderName, ReleaseDecision
from evalops.domain.errors import DomainValidationError, EvalOpsError
from evalops.domain.ids import EntityId, new_id
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics

__all__ = [
    "CaseOrigin",
    "DomainValidationError",
    "EntityId",
    "EvalOpsError",
    "EvaluatorFamily",
    "EvaluatorScore",
    "ProviderName",
    "ReleaseDecision",
    "UsageMetrics",
    "new_id",
]
