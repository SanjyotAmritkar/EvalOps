"""Domain-layer exception types."""


class EvalOpsError(Exception):
    """Base class for every EvalOps-specific error."""


class DomainValidationError(EvalOpsError):
    """Raised when a domain object would be constructed in an invalid state."""
