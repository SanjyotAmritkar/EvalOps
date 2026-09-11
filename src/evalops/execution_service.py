"""Persisted experiment execution -- the orchestration layer.

This is deliberately independent of HTTP: it takes an experiment **id** plus the
non-persisted run configuration, loads every entity it needs from the
repositories, runs the Phase 1 evaluation pipeline, persists the resulting
``EvaluationRun`` / ``CaseResult`` / ``EvaluationResult`` records, applies the
release gate, and returns a summary.

Two entry points, differing only in who owns the transaction:

* :func:`execute_experiment` -- the caller supplies an open
  :class:`~sqlalchemy.orm.Session` and owns commit/rollback (the FastAPI
  request path uses this, via its request-scoped unit of work).
* :func:`execute_experiment_in_uow` -- opens its own unit of work around the
  call; for callers with no request-scoped session (a background worker, from
  CP 4.2 onward).

Neither entry point commits the caller's session itself; persistence is only
made durable by the surrounding unit of work.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.api.schemas import RunResponse
from evalops.db import (
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    ExperimentRepository,
    PersistenceError,
    ProjectRepository,
    RecordConflict,
    RecordNotFound,
    ReleasePolicyRepository,
    SystemVersionRepository,
    unit_of_work,
)
from evalops.evaluators import build_evaluators
from evalops.execution import ExecutionSpec, build_providers, run_evaluation
from evalops.obs.context import correlation_scope
from evalops.obs.logging import get_logger, log_event
from evalops.obs.redact import safe_error

_T = TypeVar("_T")
_logger = get_logger("execution")


def _require(value: _T | None, kind: str, ref: str) -> _T:
    if value is None:
        raise PersistenceError(f"{kind} {ref!r} referenced by the experiment is missing")
    return value


def execute_experiment(
    session: Session,
    experiment_id: str,
    execution: ExecutionSpec,
    evaluator_specs: Sequence[Mapping[str, Any]],
) -> RunResponse:
    """Load, run, persist, and gate experiment ``experiment_id`` on ``session``.

    The caller owns the transaction -- nothing here commits or rolls back the
    supplied session. Raises:

    * :class:`RecordNotFound` if no such experiment (HTTP 404),
    * :class:`RecordConflict` if it has already been run; runs are never
      overwritten (HTTP 409),
    * :class:`~evalops.errors.ConfigError` for bad evaluator/execution specs and
      :class:`~evalops.domain.errors.DomainValidationError` for invalid domain
      state (HTTP 422),
    * :class:`PersistenceError` if a referenced entity is missing (HTTP 500).

    Provider failures for individual cases are recorded as failed
    ``EvaluationRun`` rows, not raised -- the run still succeeds.
    """
    experiment = ExperimentRepository(session).get(experiment_id)
    if experiment is None:
        raise RecordNotFound(f"experiment {experiment_id!r} not found")

    runs_repo = EvaluationRunRepository(session)
    if runs_repo.list_for_experiment(experiment.id):
        raise RecordConflict(
            f"experiment {experiment.id!r} has already been run; its results are immutable"
        )

    _require(
        ProjectRepository(session).get(experiment.project_id),
        "project",
        experiment.project_id,
    )
    dataset = _require(
        DatasetRepository(session).get(experiment.dataset_id),
        "dataset",
        experiment.dataset_id,
    )
    baseline = _require(
        SystemVersionRepository(session).get(experiment.baseline_version_id),
        "baseline system version",
        experiment.baseline_version_id,
    )
    candidate = _require(
        SystemVersionRepository(session).get(experiment.candidate_version_id),
        "candidate system version",
        experiment.candidate_version_id,
    )
    policy: domain.ReleasePolicy | None = None
    if experiment.release_policy_id is not None:
        policy = _require(
            ReleasePolicyRepository(session).get(experiment.release_policy_id),
            "release policy",
            experiment.release_policy_id,
        )

    with correlation_scope(experiment_id=experiment.id, project_id=experiment.project_id):
        started = time.perf_counter()
        log_event(
            _logger,
            "experiment_started",
            dataset_id=experiment.dataset_id,
            baseline_version_id=experiment.baseline_version_id,
            candidate_version_id=experiment.candidate_version_id,
            repeats=experiment.repeats,
            evaluator_count=len(evaluator_specs),
            backend=execution.backend,
        )
        try:
            evaluators = build_evaluators(evaluator_specs)
            providers = build_providers(execution, baseline, candidate)
            evaluation = run_evaluation(
                experiment,
                dataset,
                baseline,
                candidate,
                policy,
                evaluators=evaluators,
                providers=providers,
            )

            log_event(
                _logger,
                "release_decision_computed",
                decision=evaluation.gate.decision.value,
                gated=evaluation.gate.gated,
                blocking_metrics=len(evaluation.gate.reasons),
                advisories=len(evaluation.gate.advisories),
            )

            for run in evaluation.outcome.runs:
                runs_repo.add(run)
            for case_result in evaluation.outcome.case_results:
                runs_repo.add_case_result(case_result)
            stored = EvaluationResultRepository(session).add(evaluation.result)
        except Exception as exc:
            log_event(
                _logger,
                "experiment_failed",
                level=logging.ERROR,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                error_type=type(exc).__name__,
                error=safe_error(exc),
            )
            raise

        runs = list(evaluation.outcome.runs)
        log_event(
            _logger,
            "experiment_completed",
            evaluation_result_id=stored.id,
            run_count=len(runs),
            failure_count=sum(1 for r in runs if r.error is not None),
            decision=evaluation.gate.decision.value,
            gated=evaluation.gate.gated,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    return RunResponse.of(
        experiment=experiment,
        dataset=dataset,
        baseline=baseline,
        candidate=candidate,
        runs=runs,
        result=evaluation.result,
        gate=evaluation.gate,
        evaluation_result_id=stored.id,
    )


def execute_experiment_in_uow(
    sessions: sessionmaker[Session],
    experiment_id: str,
    execution: ExecutionSpec,
    evaluator_specs: Sequence[Mapping[str, Any]],
) -> RunResponse:
    """Run :func:`execute_experiment` inside its own unit of work.

    For callers with no request-scoped session (a background worker). Commits on
    success, rolls back on any error, always closes the session. The return
    value stays valid after commit (the session factory uses
    ``expire_on_commit=False``).
    """
    with unit_of_work(sessions) as session:
        return execute_experiment(session, experiment_id, execution, evaluator_specs)
