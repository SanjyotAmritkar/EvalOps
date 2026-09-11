"""Concurrency-safe correlation context.

A single :class:`contextvars.ContextVar` holds the correlation identifiers for
the unit of work currently executing -- one HTTP request, or one Celery task.
``contextvars`` gives each ``asyncio`` task and each thread its own view, so
concurrent requests never see each other's ids, and the value is restored on
scope exit via the token returned by :func:`bind`.

No process-global mutable dict. Nothing here logs, persists, or knows about
FastAPI/Celery -- callers at those boundaries populate it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from types import MappingProxyType

#: The correlation fields propagated through a lifecycle. All optional; a value
#: is only present once a boundary has set it.
FIELDS: tuple[str, ...] = (
    "request_id",
    "project_id",
    "experiment_id",
    "job_id",
    "celery_task_id",
)

#: Immutable empty default -- the value is only ever replaced via ``.set()`` with
#: a fresh dict, never mutated in place.
_EMPTY: Mapping[str, str] = MappingProxyType({})
_context: ContextVar[Mapping[str, str]] = ContextVar("evalops_correlation", default=_EMPTY)


def get_context() -> dict[str, str]:
    """A copy of the correlation fields currently in scope."""
    return dict(_context.get())


def get_field(name: str) -> str | None:
    """One correlation field, or ``None`` if unset."""
    return _context.get().get(name)


def bind(**fields: str | None) -> Token[Mapping[str, str]]:
    """Merge ``fields`` (dropping ``None``) into the correlation context.

    Returns a token; pass it to :func:`reset` to restore the previous value.
    Prefer the :func:`context` context manager, which resets for you.
    """
    merged = dict(_context.get())
    for key, value in fields.items():
        if value is not None:
            merged[key] = str(value)
    return _context.set(merged)


def reset(token: Token[Mapping[str, str]]) -> None:
    """Restore the correlation context to the value captured by ``token``."""
    _context.reset(token)


@contextmanager
def correlation_scope(**fields: str | None) -> Iterator[None]:
    """Bind ``fields`` for the duration of the ``with`` block, then restore."""
    token = bind(**fields)
    try:
        yield
    finally:
        reset(token)


def snapshot_for_dispatch() -> dict[str, str]:
    """The subset of the context worth carrying across the Celery boundary.

    ``job_id`` / ``celery_task_id`` are assigned on the worker side, so only the
    originating ``request_id`` (and ``experiment_id`` when already known) travel
    with the task payload.
    """
    ctx = _context.get()
    return {k: ctx[k] for k in ("request_id", "experiment_id") if k in ctx}
