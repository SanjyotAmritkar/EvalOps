"""Persistence-layer error types."""

from evalops.domain.errors import EvalOpsError


class PersistenceError(EvalOpsError):
    """Base class for persistence failures."""


class RecordConflict(PersistenceError):
    """A write violated a uniqueness or referential-integrity constraint.

    Covers both duplicate primary/unique keys and dangling foreign keys.
    """


__all__ = ["PersistenceError", "RecordConflict"]
