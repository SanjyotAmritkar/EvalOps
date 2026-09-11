"""EvalOps observability layer (Phase 10, CP 10.3).

A small coherent surface over the standard library:

* :mod:`~evalops.obs.context` -- concurrency-safe correlation ids
  (``request_id`` / ``project_id`` / ``experiment_id`` / ``job_id`` /
  ``celery_task_id``) via ``contextvars``.
* :mod:`~evalops.obs.logging` -- structured JSON (or console) logging and the
  :func:`log_event` helper with stable event names.
* :mod:`~evalops.obs.redact` -- sanitisation so keys / prompts / outputs never
  reach a log line.
* :mod:`~evalops.obs.settings` -- safe operational metadata from the env.
* :mod:`~evalops.obs.middleware` -- the pure-ASGI request-context middleware.

Nothing here changes evaluation, statistical, gate, diagnostics, persistence or
provider semantics.
"""

from __future__ import annotations

from evalops.obs.context import (
    bind,
    correlation_scope,
    get_context,
    get_field,
    reset,
    snapshot_for_dispatch,
)
from evalops.obs.logging import configure_logging, get_logger, log_event
from evalops.obs.redact import error_type, redact, safe_error, safe_str
from evalops.obs.settings import ObservabilitySettings

__all__ = [
    "ObservabilitySettings",
    "bind",
    "configure_logging",
    "correlation_scope",
    "error_type",
    "get_context",
    "get_field",
    "get_logger",
    "log_event",
    "redact",
    "reset",
    "safe_error",
    "safe_str",
    "snapshot_for_dispatch",
]
