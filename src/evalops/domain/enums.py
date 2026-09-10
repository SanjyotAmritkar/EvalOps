"""Enumerations shared across the domain model.

The string values are a serialization contract: they appear in evaluation
config files, stored records, and API payloads, so they must stay stable.
"""

from enum import StrEnum


class ProviderName(StrEnum):
    """Model providers EvalOps can target: two hosted plus one local."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class EvaluatorFamily(StrEnum):
    """The evaluator families defined in docs/ARCHITECTURE.md section 6."""

    DETERMINISTIC = "deterministic"
    STATISTICAL = "statistical"
    LLM_JUDGE = "llm_judge"


class CaseOrigin(StrEnum):
    """How a DatasetCase entered its dataset."""

    AUTHORED = "authored"
    PROMOTED_TRACE = "promoted_trace"


class TraceOrigin(StrEnum):
    """Where a ProductionTrace came from.

    Only real production traffic is modelled in Phase 8; the enum exists so the
    source is an explicit, extensible marker rather than an implicit assumption.
    """

    PRODUCTION = "production"


class ReleaseDecision(StrEnum):
    """The outcome of applying a ReleasePolicy to an EvaluationResult."""

    PASS = "pass"
    BLOCK = "block"
    NEEDS_REVIEW = "needs_review"


class JobStatus(StrEnum):
    """Lifecycle of a background (async) experiment run. Terminal: completed / failed."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
