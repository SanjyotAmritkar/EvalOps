"""Cross-cutting error types for the evalops application layer."""

from evalops.domain.errors import EvalOpsError


class ConfigError(EvalOpsError):
    """Raised when user-supplied input (dataset, config, CLI args) is invalid.

    Carries a human-facing message suitable for printing to stderr. The CLI
    maps it to exit code 2.
    """


__all__ = ["ConfigError", "EvalOpsError"]
