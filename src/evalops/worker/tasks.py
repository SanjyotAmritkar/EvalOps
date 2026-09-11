"""Background experiment execution with a durable job lifecycle.

An :class:`~evalops.domain.AsyncJob` row in PostgreSQL -- not Celery -- is the
authoritative record of an async run: ``queued -> running -> completed | failed``.

* :func:`enqueue_experiment_run` writes a ``queued`` job, then dispatches the
  task. (Nothing HTTP calls this yet.)
* :func:`execute_experiment_task` receives the **job id**, marks it ``running``,
  delegates to :func:`evalops.execution_service.execute_experiment_in_uow`
  (unchanged), then marks the job ``completed`` (+ result link) or ``failed``
  (+ bounded error) and re-raises so the Celery task still fails.

Each job-state transition is its own unit of work, separate from the evaluation
transaction, so a failed evaluation can still be recorded as a failed job
rather than leaving the job stuck at ``running``.

CP 10.3 adds structured lifecycle events (``async_job_queued`` / ``_started`` /
``_completed`` / ``_failed``) and carries the originating ``request_id`` across
the broker in the task payload. No job-state semantics change; no retries.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.api.schemas import ExecutionOptions
from evalops.db import AsyncJobRepository, RecordNotFound, unit_of_work
from evalops.execution_service import execute_experiment_in_uow
from evalops.obs.context import correlation_scope, snapshot_for_dispatch
from evalops.obs.logging import configure_logging, get_logger, log_event
from evalops.obs.redact import safe_error
from evalops.worker.celery_app import celery_app, get_session_factory

configure_logging()
_logger = get_logger("worker")


class DispatchError(domain.EvalOpsError):
    """The ``async_job`` row was committed but the Celery broker could not be
    reached to enqueue the task. The job is marked ``failed`` before this is
    raised, so the persisted state stays truthful."""


def enqueue_experiment_run(
    experiment_id: str,
    execution: dict[str, Any],
    evaluators: list[dict[str, Any]],
    *,
    sessions: sessionmaker[Session] | None = None,
) -> domain.AsyncJob:
    """Create a queued :class:`~evalops.domain.AsyncJob` and dispatch the task.

    Returns the persisted ``queued`` job. The job row is committed (its own unit
    of work) before the task is dispatched, so the worker can always find it.

    * :class:`~evalops.db.RecordConflict` if ``experiment_id`` does not exist
      (foreign key).
    * :class:`DispatchError` if the broker is unreachable -- the job is marked
      ``failed`` first, so ``GET /jobs/{id}`` reflects reality.
    """
    factory = sessions or get_session_factory()
    job = domain.AsyncJob(experiment_id=experiment_id)
    with unit_of_work(factory) as session:
        AsyncJobRepository(session).add(job)

    with correlation_scope(job_id=job.id, experiment_id=experiment_id):
        log_event(_logger, "async_job_queued", job_id=job.id, experiment_id=experiment_id)

        # Carry the originating request_id (+ experiment_id) across the broker.
        correlation = snapshot_for_dispatch()
        try:
            execute_experiment_task.delay(job.id, execution, evaluators, correlation)
        except Exception as exc:  # broker unreachable, serialization error, ...
            with unit_of_work(factory) as session:
                AsyncJobRepository(session).mark_failed(
                    job.id,
                    f"dispatch to the task broker failed: {type(exc).__name__}: {exc}",
                )
            log_event(
                _logger,
                "async_job_dispatch_failed",
                level=logging.ERROR,
                job_id=job.id,
                experiment_id=experiment_id,
                error_type=type(exc).__name__,
                error=safe_error(exc),
            )
            raise DispatchError(
                f"async job {job.id!r} was recorded but could not be dispatched: {exc}"
            ) from exc

    return job


@celery_app.task(bind=True, name="evalops.execute_experiment")
def execute_experiment_task(
    self: Any,
    job_id: str,
    execution: dict[str, Any],
    evaluators: list[dict[str, Any]],
    correlation: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run the experiment behind async job ``job_id``.

    ``execution`` / ``evaluators`` are the same JSON shapes
    ``POST /experiments/{id}/run`` accepts. ``correlation`` carries the
    originating ``request_id`` when the run came from HTTP. Returns the
    ``RunResponse`` as a JSON-safe dict on success; on failure the job is marked
    ``failed`` and the original exception is re-raised (the Celery task fails
    too).
    """
    factory = get_session_factory()
    celery_task_id = getattr(self.request, "id", None)

    with correlation_scope(
        **(correlation or {}),
        job_id=job_id,
        celery_task_id=celery_task_id,
    ):
        started = time.perf_counter()

        # queued -> running -- its own transaction, committed before evaluation.
        with unit_of_work(factory) as session:
            jobs = AsyncJobRepository(session)
            job = jobs.get(job_id)
            if job is None:
                raise RecordNotFound(f"async job {job_id!r} not found")
            experiment_id = job.experiment_id
            jobs.mark_running(job_id, celery_task_id=celery_task_id)

        with correlation_scope(experiment_id=experiment_id):
            log_event(
                _logger,
                "async_job_started",
                job_id=job_id,
                experiment_id=experiment_id,
                celery_task_id=celery_task_id,
            )
            try:
                spec = ExecutionOptions.model_validate(execution).to_spec()
                response = execute_experiment_in_uow(factory, experiment_id, spec, evaluators)
            except Exception as exc:
                # running -> failed -- a fresh transaction, so it commits even
                # though the evaluation transaction rolled back.
                with unit_of_work(factory) as session:
                    AsyncJobRepository(session).mark_failed(job_id, f"{type(exc).__name__}: {exc}")
                log_event(
                    _logger,
                    "async_job_failed",
                    level=logging.ERROR,
                    job_id=job_id,
                    experiment_id=experiment_id,
                    celery_task_id=celery_task_id,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    error_type=type(exc).__name__,
                    error=safe_error(exc),
                )
                raise

            # running -> completed (+ result link) -- its own transaction.
            with unit_of_work(factory) as session:
                AsyncJobRepository(session).mark_completed(job_id, response.evaluation_result_id)
            log_event(
                _logger,
                "async_job_completed",
                job_id=job_id,
                experiment_id=experiment_id,
                celery_task_id=celery_task_id,
                evaluation_result_id=response.evaluation_result_id,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            return response.model_dump(mode="json")
