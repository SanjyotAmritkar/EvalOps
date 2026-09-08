"""Application service: execute a persisted experiment and store its results.

Orchestration only -- it loads the experiment graph from the repositories,
runs the existing evaluation pipeline via :func:`evalops.execution.run_evaluation`,
persists every EvaluationRun / CaseResult / EvaluationResult, and returns a
summary. HTTP concerns stay in the routes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from evalops import domain
from evalops.api.schemas import RunResponse
from evalops.db import (
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    PersistenceError,
    ProjectRepository,
    RecordConflict,
    ReleasePolicyRepository,
    SystemVersionRepository,
)
from evalops.evaluators import build_evaluators
from evalops.execution import ExecutionSpec, build_providers, run_evaluation

_T = TypeVar("_T")


def _require(value: _T | None, kind: str, ref: str) -> _T:
    if value is None:
        raise PersistenceError(f"{kind} {ref!r} referenced by the experiment is missing")
    return value


def execute_experiment(
    session: Session,
    experiment: domain.Experiment,
    execution: ExecutionSpec,
    evaluator_specs: Sequence[Mapping[str, Any]],
) -> RunResponse:
    """Run ``experiment`` and persist its runs and result.

    Raises :class:`RecordConflict` if the experiment has already been run (its
    runs are never overwritten). Bad evaluator/execution specs raise
    ``ConfigError``; invalid domain state raises ``DomainValidationError``.
    """
    runs_repo = EvaluationRunRepository(session)
    if runs_repo.list_for_experiment(experiment.id):
        raise RecordConflict(
            f"experiment {experiment.id!r} has already been run; its results are immutable"
        )

    _require(
        ProjectRepository(session).get(experiment.project_id), "project", experiment.project_id
    )
    dataset = _require(
        DatasetRepository(session).get(experiment.dataset_id), "dataset", experiment.dataset_id
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

    for run in evaluation.outcome.runs:
        runs_repo.add(run)
    for case_result in evaluation.outcome.case_results:
        runs_repo.add_case_result(case_result)
    stored = EvaluationResultRepository(session).add(evaluation.result)

    return RunResponse.of(
        experiment=experiment,
        dataset=dataset,
        baseline=baseline,
        candidate=candidate,
        runs=list(evaluation.outcome.runs),
        result=evaluation.result,
        gate=evaluation.gate,
        evaluation_result_id=stored.id,
    )
