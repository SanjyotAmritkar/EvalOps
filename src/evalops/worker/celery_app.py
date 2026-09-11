"""Celery application and worker configuration.

* Broker: Redis (``CELERY_BROKER_URL``, default ``redis://localhost:6379/0`` --
  matches ``infra/docker-compose.yml`` / ``docker-compose.yml``).
* No result backend: authoritative evaluation output is the ``EvaluationRun`` /
  ``EvaluationResult`` rows the execution service writes to PostgreSQL. Celery
  only moves tasks; task return values are for logs / eager tests, not storage.
* JSON task payloads only.

CP 10.4 -- delivery semantics (read this before touching any acks/retry setting)
================================================================================

``evalops.execute_experiment`` calls real, possibly nondeterministic, possibly
billed model providers. Re-executing it is never free and never idempotent, so
this module deliberately keeps Celery's **at-most-once** task delivery rather
than the at-least-once behaviour Celery can offer:

* ``task_acks_late=False`` (Celery's own default, set explicitly here) --
  a task is acknowledged to the broker the moment a worker *receives* it, not
  after it finishes. If the worker process dies mid-execution, Redis has
  already forgotten the task: nobody re-delivers it, so the evaluation never
  runs twice.
* ``task_reject_on_worker_lost=False`` -- the complementary setting; it only
  has an effect when ``task_acks_late=True``, but is set explicitly so the
  "never redeliver an in-flight evaluation" intent is not implicit.

The cost of that choice is what CP 10.4's docs call the **stale job**: if a
worker dies after marking an ``async_job`` row ``running``, that row is never
moved to ``completed``/``failed`` by anyone (Redis will not redeliver, and
there is no reaper in this checkpoint). See ``docs/ARCHITECTURE.md`` CP 10.4
for why this is safe (the run is transactional -- a dead worker leaves either
a fully persisted result or nothing at all, never a partial one) and the
manual recovery procedure. Broker *connection* recovery (reconnecting to Redis
after a network blip) is a different, safe category and stays enabled via
``broker_connection_retry`` / ``broker_connection_retry_on_startup`` below --
that retries moving bytes to a broker, never a model call.

No ``autoretry_for`` / task-level retry is configured, and none should be
added without re-reading this note.
"""

from __future__ import annotations

import os

from celery import Celery
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import session_factory
from evalops.obs.logging import configure_logging

#: Local development default; overridden by ``CELERY_BROKER_URL``.
DEFAULT_BROKER_URL = "redis://localhost:6379/0"

#: A generous safety net against a genuinely hung task (a provider client that
#: never returns) tying up a worker slot forever -- not a correctness
#: mechanism, and not a retry: when the soft limit fires, the existing
#: ``except Exception`` in ``execute_experiment_task`` marks the job ``failed``
#: exactly as any other exception would (``SoftTimeLimitExceeded`` is a plain
#: ``Exception`` subclass). The hard limit is the backstop if that handler
#: itself hangs. ``0``/unset disables both -- a legitimate large real-provider
#: run can legitimately take a long time.
DEFAULT_SOFT_TIME_LIMIT_S = 1800.0  # 30 minutes
DEFAULT_TIME_LIMIT_S = 1900.0  # ~31.7 minutes; > soft, so soft fires first


def broker_url() -> str:
    """Redis broker URL from ``CELERY_BROKER_URL`` (or the local default)."""
    return os.environ.get("CELERY_BROKER_URL", DEFAULT_BROKER_URL)


def _time_limit_env(name: str, default: float) -> float | None:
    """A positive float from the environment, ``None`` if unset/``0``/invalid."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default if default > 0 else None
    try:
        value = float(raw)
    except ValueError:
        return default if default > 0 else None
    return value if value > 0 else None


def create_celery_app() -> Celery:
    # Structured logging for the worker process too (root logger is not hijacked;
    # see worker_hijack_root_logger below).
    configure_logging()
    app = Celery("evalops", broker=broker_url())
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_backend=None,  # explicit: nothing authoritative is stored in Redis
        timezone="UTC",
        enable_utc=True,
        worker_hijack_root_logger=False,
        # --- (A) broker/infrastructure reconnection -- always safe to retry ---
        # Retry the broker connection while the worker starts (Celery 6 default;
        # setting it silences the 5.x startup warning) and during normal
        # operation if the connection drops. Neither re-executes a task; both
        # only concern reconnecting the transport.
        broker_connection_retry_on_startup=True,
        broker_connection_retry=True,
        # --- (B)/(C) evaluation task delivery -- deliberately NOT at-least-once,
        # see the module docstring for why. ------------------------------------
        task_acks_late=False,
        task_reject_on_worker_lost=False,
        # A hung task is killed cleanly rather than occupying a worker forever;
        # it is never automatically redelivered/retried when it happens.
        task_soft_time_limit=_time_limit_env(
            "CELERY_TASK_SOFT_TIME_LIMIT_S", DEFAULT_SOFT_TIME_LIMIT_S
        ),
        task_time_limit=_time_limit_env("CELERY_TASK_TIME_LIMIT_S", DEFAULT_TIME_LIMIT_S),
        # Fair dispatch for long-running tasks: a worker does not hoard several
        # evaluation runs while another worker sits idle. Independent of the
        # ack semantics above (prefetch only affects which idle worker a
        # not-yet-started task goes to).
        worker_prefetch_multiplier=1,
    )
    app.autodiscover_tasks(["evalops.worker"])
    return app


celery_app = create_celery_app()


#: One SQLAlchemy session factory per worker process, built lazily on first task
#: so the engine (and its connection pool) is created after the prefork, never
#: shared across a fork.
_sessions: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    """The worker's own session factory, configured from ``DATABASE_URL``.

    Not a request-scoped session -- the worker owns its transactions via
    :func:`evalops.execution_service.execute_experiment_in_uow`.
    """
    global _sessions
    if _sessions is None:
        _sessions = session_factory()
    return _sessions
