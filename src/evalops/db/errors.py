"""Persistence-layer error types."""

from evalops.domain.errors import EvalOpsError


class PersistenceError(EvalOpsError):
    """Base class for persistence failures."""


class RecordConflict(PersistenceError):
    """A write violated a uniqueness or referential-integrity constraint.

    Covers both duplicate primary/unique keys and dangling foreign keys.
    """


class RecordNotFound(PersistenceError):
    """A record addressed by id does not exist.

    The lookup analogue of :class:`RecordConflict`: raised by services that load
    an entity by id and cannot proceed without it.
    """


__all__ = ["PersistenceError", "RecordConflict", "RecordNotFound"]
