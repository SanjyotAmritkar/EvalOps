"""Celery application and worker configuration.

* Broker: Redis (``CELERY_BROKER_URL``, default ``redis://localhost:6379/0`` --
  matches ``infra/docker-compose.yml``).
* No result backend: authoritative evaluation output is the ``EvaluationRun`` /
  ``EvaluationResult`` rows the execution service writes to PostgreSQL. Celery
  only moves tasks; task return values are for logs / eager tests, not storage.
* JSON task payloads only.
"""

from __future__ import annotations

import os

from celery import Celery
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import session_factory
from evalops.obs.logging import configure_logging

#: Local development default; overridden by ``CELERY_BROKER_URL``.
DEFAULT_BROKER_URL = "redis://localhost:6379/0"


def broker_url() -> str:
    """Redis broker URL from ``CELERY_BROKER_URL`` (or the local default)."""
    return os.environ.get("CELERY_BROKER_URL", DEFAULT_BROKER_URL)


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
        # Retry the broker connection while the worker starts (Celery 6 default;
        # setting it silences the 5.x startup warning). Not a task retry.
        broker_connection_retry_on_startup=True,
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
