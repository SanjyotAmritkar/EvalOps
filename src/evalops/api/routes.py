"""API routes: thin handlers over the repository + unit-of-work layer.

No raw SQLAlchemy here -- every read/write goes through a repository. Existence
of referenced resources is checked explicitly and returns 404; uniqueness /
foreign-key conflicts surface as 409 and domain-invariant violations as 422
via the exception handlers registered in ``main``.
"""

from __future__ import annotations

from typing import TypeVar

from fastapi import APIRouter, HTTPException, status

from evalops import domain
from evalops.api.deps import SessionDep
from evalops.api.schemas import (
    DatasetCreate,
    DatasetRead,
    EvaluationResultRead,
    EvaluationRunRead,
    ExperimentCreate,
    ExperimentRead,
    ProjectCreate,
    ProjectRead,
    ReleasePolicyCreate,
    ReleasePolicyRead,
    RunRequest,
    RunResponse,
    SystemVersionCreate,
    SystemVersionRead,
)
from evalops.api.service import execute_experiment
from evalops.db import (
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    ExperimentRepository,
    ProjectRepository,
    ReleasePolicyRepository,
    SystemVersionRepository,
)
from evalops.gate import evaluate_gate

_T = TypeVar("_T")


def _found(value: _T | None, detail: str) -> _T:
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return value


projects = APIRouter(tags=["projects"])
datasets = APIRouter(tags=["datasets"])
system_versions = APIRouter(tags=["system-versions"])
release_policies = APIRouter(tags=["release-policies"])
experiments = APIRouter(tags=["experiments"])


# --- projects ---------------------------------------------------------


@projects.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectRead:
    project = ProjectRepository(session).add(domain.Project(name=body.name))
    return ProjectRead.of(project)


@projects.get("/projects")
def list_projects(session: SessionDep) -> list[ProjectRead]:
    return [ProjectRead.of(p) for p in ProjectRepository(session).list_all()]


@projects.get("/projects/{project_id}")
def get_project(project_id: str, session: SessionDep) -> ProjectRead:
    return ProjectRead.of(_found(ProjectRepository(session).get(project_id), "project not found"))


# --- datasets --------------------------------------------------------


@datasets.post("/projects/{project_id}/datasets", status_code=status.HTTP_201_CREATED)
def create_dataset(project_id: str, body: DatasetCreate, session: SessionDep) -> DatasetRead:
    _found(ProjectRepository(session).get(project_id), "project not found")
    dataset = domain.Dataset(
        project_id=project_id,
        name=body.name,
        version=body.version,
        cases=tuple(
            domain.DatasetCase(
                input=case.input,
                expected_output=case.expected_output,
                origin=case.origin,
                source_trace_id=case.source_trace_id,
            )
            for case in body.cases
        ),
    )
    return DatasetRead.of(DatasetRepository(session).add(dataset))


@datasets.get("/projects/{project_id}/datasets")
def list_datasets(project_id: str, session: SessionDep) -> list[DatasetRead]:
    _found(ProjectRepository(session).get(project_id), "project not found")
    return [DatasetRead.of(d) for d in DatasetRepository(session).list_for_project(project_id)]


@datasets.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: SessionDep) -> DatasetRead:
    return DatasetRead.of(_found(DatasetRepository(session).get(dataset_id), "dataset not found"))


# --- system versions --------------------------------------------


@system_versions.post("/projects/{project_id}/system-versions", status_code=status.HTTP_201_CREATED)
def create_system_version(
    project_id: str, body: SystemVersionCreate, session: SessionDep
) -> SystemVersionRead:
    _found(ProjectRepository(session).get(project_id), "project not found")
    version = domain.SystemVersion(
        project_id=project_id,
        name=body.name,
        version=body.version,
        provider=body.provider,
        model=body.model,
        prompt_template=body.prompt_template,
        parameters=body.parameters,
        rag_config=body.rag_config,
        tool_policy=body.tool_policy,
    )
    return SystemVersionRead.of(SystemVersionRepository(session).add(version))


@system_versions.get("/projects/{project_id}/system-versions")
def list_system_versions(project_id: str, session: SessionDep) -> list[SystemVersionRead]:
    _found(ProjectRepository(session).get(project_id), "project not found")
    return [
        SystemVersionRead.of(v)
        for v in SystemVersionRepository(session).list_for_project(project_id)
    ]


@system_versions.get("/system-versions/{system_version_id}")
def get_system_version(system_version_id: str, session: SessionDep) -> SystemVersionRead:
    return SystemVersionRead.of(
        _found(
            SystemVersionRepository(session).get(system_version_id),
            "system version not found",
        )
    )


# --- release policies -----------------------------------------


@release_policies.post("/release-policies", status_code=status.HTTP_201_CREATED)
def create_release_policy(body: ReleasePolicyCreate, session: SessionDep) -> ReleasePolicyRead:
    policy = domain.ReleasePolicy(
        name=body.name,
        thresholds=body.thresholds,
        max_safety_violations=body.max_safety_violations,
    )
    return ReleasePolicyRead.of(ReleasePolicyRepository(session).add(policy))


@release_policies.get("/release-policies")
def list_release_policies(session: SessionDep) -> list[ReleasePolicyRead]:
    return [ReleasePolicyRead.of(p) for p in ReleasePolicyRepository(session).list_all()]


@release_policies.get("/release-policies/{policy_id}")
def get_release_policy(policy_id: str, session: SessionDep) -> ReleasePolicyRead:
    return ReleasePolicyRead.of(
        _found(ReleasePolicyRepository(session).get(policy_id), "release policy not found")
    )


# --- experiments ----------------------------------------------


@experiments.post("/projects/{project_id}/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(
    project_id: str, body: ExperimentCreate, session: SessionDep
) -> ExperimentRead:
    _found(ProjectRepository(session).get(project_id), "project not found")
    _found(DatasetRepository(session).get(body.dataset_id), "dataset not found")
    _found(
        SystemVersionRepository(session).get(body.baseline_version_id),
        "baseline system version not found",
    )
    _found(
        SystemVersionRepository(session).get(body.candidate_version_id),
        "candidate system version not found",
    )
    if body.release_policy_id is not None:
        _found(
            ReleasePolicyRepository(session).get(body.release_policy_id),
            "release policy not found",
        )
    experiment = domain.Experiment(
        project_id=project_id,
        dataset_id=body.dataset_id,
        baseline_version_id=body.baseline_version_id,
        candidate_version_id=body.candidate_version_id,
        repeats=body.repeats,
        release_policy_id=body.release_policy_id,
    )
    return ExperimentRead.of(ExperimentRepository(session).add(experiment))


@experiments.get("/projects/{project_id}/experiments")
def list_experiments(project_id: str, session: SessionDep) -> list[ExperimentRead]:
    _found(ProjectRepository(session).get(project_id), "project not found")
    return [
        ExperimentRead.of(e) for e in ExperimentRepository(session).list_for_project(project_id)
    ]


@experiments.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, session: SessionDep) -> ExperimentRead:
    return ExperimentRead.of(
        _found(ExperimentRepository(session).get(experiment_id), "experiment not found")
    )


@experiments.post("/experiments/{experiment_id}/run", status_code=status.HTTP_201_CREATED)
def run_experiment_route(experiment_id: str, body: RunRequest, session: SessionDep) -> RunResponse:
    experiment = _found(ExperimentRepository(session).get(experiment_id), "experiment not found")
    return execute_experiment(
        session,
        experiment,
        body.execution.to_spec(),
        [spec.model_dump(exclude_none=True) for spec in body.evaluators],
    )


@experiments.get("/experiments/{experiment_id}/runs")
def list_experiment_runs(experiment_id: str, session: SessionDep) -> list[EvaluationRunRead]:
    _found(ExperimentRepository(session).get(experiment_id), "experiment not found")
    repo = EvaluationRunRepository(session)
    return [
        EvaluationRunRead.of(run, repo.get_case_result_for_run(run.id))
        for run in repo.list_for_experiment(experiment_id)
    ]


@experiments.get("/experiments/{experiment_id}/results")
def list_experiment_results(experiment_id: str, session: SessionDep) -> list[EvaluationResultRead]:
    experiment = _found(ExperimentRepository(session).get(experiment_id), "experiment not found")
    policy = (
        None
        if experiment.release_policy_id is None
        else _found(
            ReleasePolicyRepository(session).get(experiment.release_policy_id),
            "release policy not found",
        )
    )
    # G-1: the release decision is not persisted -- recompute it from the stored
    # result + policy with the same evaluate_gate the run path uses.
    return [
        EvaluationResultRead.of(result, evaluate_gate(result, policy))
        for result in EvaluationResultRepository(session).list_for_experiment(experiment_id)
    ]


ROUTERS = (projects, datasets, system_versions, release_policies, experiments)
