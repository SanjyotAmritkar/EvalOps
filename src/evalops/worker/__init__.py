"""Background execution: a Celery worker that runs the persisted execution
service off the request path.

Redis is broker-only. PostgreSQL stays the source of truth -- the worker
persists ``EvaluationRun`` / ``EvaluationResult`` rows through
:func:`evalops.execution_service.execute_experiment_in_uow`, exactly as the
synchronous API path does.
"""

from evalops.worker.celery_app import celery_app

__all__ = ["celery_app"]
