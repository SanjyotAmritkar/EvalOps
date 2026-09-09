"""Cross-cutting error types for the evalops application layer."""

from evalops.domain.errors import EvalOpsError


class ConfigError(EvalOpsError):
    """Raised when user-supplied input (dataset, config, CLI args) is invalid.

    Carries a human-facing message suitable for printing to stderr. The CLI
    maps it to exit code 2.
    """


class JudgeError(EvalOpsError):
    """Raised when an LLM judge returns output that cannot be parsed into a
    verdict. Distinct from ``ProviderError``: the provider call itself
    succeeded, but its content is unusable. Must fail loudly -- never a silent
    pass. The CLI maps it to exit code 2; the API to HTTP 502.
    """


__all__ = ["ConfigError", "EvalOpsError", "JudgeError"]
