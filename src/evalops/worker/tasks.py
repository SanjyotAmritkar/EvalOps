"""The one background task: run a persisted experiment.

This module contains no evaluation, gating, or persistence logic. It converts a
JSON-serializable payload into the internal config and delegates to
:func:`evalops.execution_service.execute_experiment_in_uow`.
"""

from __future__ import annotations

from typing import Any

from evalops.api.schemas import ExecutionOptions
from evalops.execution_service import execute_experiment_in_uow
from evalops.worker.celery_app import celery_app, get_session_factory


@celery_app.task(name="evalops.execute_experiment")
def execute_experiment_task(
    experiment_id: str,
    execution: dict[str, Any],
    evaluators: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute experiment ``experiment_id`` in a worker.

    Parameters are the same JSON shapes ``POST /experiments/{id}/run`` accepts:

    * ``execution`` -- an ``ExecutionOptions`` dict (``backend`` / ``base_url`` /
      ``timeout_seconds``); ``{}`` means the defaults.
    * ``evaluators`` -- the list of evaluator spec dicts (``{"type": ...}``).

    ``ExecutionOptions`` is reused to rebuild the typed ``ExecutionSpec`` (same
    validation and defaults as the HTTP path). The worker uses its own session
    factory; the execution service owns the transaction.

    Returns the ``RunResponse`` as a JSON-safe dict (for logs / eager callers);
    the authoritative ``EvaluationRun`` / ``EvaluationResult`` rows are already
    committed to PostgreSQL. A missing experiment (``RecordNotFound``), an
    already-run experiment (``RecordConflict``), or a bad spec (``ConfigError`` /
    ``ValidationError``) propagates as a task failure.
    """
    spec = ExecutionOptions.model_validate(execution).to_spec()
    response = execute_experiment_in_uow(
        get_session_factory(),
        experiment_id,
        spec,
        evaluators,
    )
    return response.model_dump(mode="json")
