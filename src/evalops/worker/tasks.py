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
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.api.schemas import ExecutionOptions
from evalops.db import AsyncJobRepository, RecordNotFound, unit_of_work
from evalops.execution_service import execute_experiment_in_uow
from evalops.worker.celery_app import celery_app, get_session_factory


def enqueue_experiment_run(
    experiment_id: str,
    execution: dict[str, Any],
    evaluators: list[dict[str, Any]],
    *,
    sessions: sessionmaker[Session] | None = None,
) -> str:
    """Create a queued :class:`~evalops.domain.AsyncJob` and dispatch the task.

    Returns the job id. The job row is committed before the task is dispatched
    so the worker can always find it. Raises
    :class:`~evalops.db.RecordConflict` if ``experiment_id`` does not exist
    (foreign key).
    """
    factory = sessions or get_session_factory()
    job = domain.AsyncJob(experiment_id=experiment_id)
    with unit_of_work(factory) as session:
        AsyncJobRepository(session).add(job)
    execute_experiment_task.delay(job.id, execution, evaluators)
    return job.id


@celery_app.task(bind=True, name="evalops.execute_experiment")
def execute_experiment_task(
    self: Any,
    job_id: str,
    execution: dict[str, Any],
    evaluators: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the experiment behind async job ``job_id``.

    ``execution`` / ``evaluators`` are the same JSON shapes
    ``POST /experiments/{id}/run`` accepts. Returns the ``RunResponse`` as a
    JSON-safe dict on success; on failure the job is marked ``failed`` and the
    original exception is re-raised (the Celery task fails too).
    """
    factory = get_session_factory()

    # queued -> running -- its own transaction, committed before evaluation.
    with unit_of_work(factory) as session:
        jobs = AsyncJobRepository(session)
        job = jobs.get(job_id)
        if job is None:
            raise RecordNotFound(f"async job {job_id!r} not found")
        experiment_id = job.experiment_id
        jobs.mark_running(job_id, celery_task_id=self.request.id)

    try:
        spec = ExecutionOptions.model_validate(execution).to_spec()
        response = execute_experiment_in_uow(factory, experiment_id, spec, evaluators)
    except Exception as exc:
        # running -> failed -- a fresh transaction, so it commits even though the
        # evaluation transaction rolled back.
        with unit_of_work(factory) as session:
            AsyncJobRepository(session).mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        raise

    # running -> completed (+ result link) -- its own transaction.
    with unit_of_work(factory) as session:
        AsyncJobRepository(session).mark_completed(job_id, response.evaluation_result_id)
    return response.model_dump(mode="json")
