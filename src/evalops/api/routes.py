"""API routes: thin handlers over the repository + unit-of-work layer.

No raw SQLAlchemy here -- every read/write goes through a repository. Existence
of referenced resources is checked explicitly and returns 404; uniqueness /
foreign-key conflicts surface as 409 and domain-invariant violations as 422
via the exception handlers registered in ``main``.
"""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, status

from evalops import domain
from evalops.api.deps import SessionDep, SessionsDep
from evalops.api.schemas import (
    AsyncJobRead,
    DatasetCreate,
    DatasetRead,
    EvaluationResultRead,
    EvaluationRunRead,
    ExperimentCreate,
    ExperimentRead,
    JudgeCalibrationCreate,
    JudgeCalibrationRead,
    ProjectCreate,
    ProjectRead,
    RegressionDiagnosticsRead,
    ReleasePolicyCreate,
    ReleasePolicyRead,
    RunRequest,
    RunResponse,
    SystemVersionCreate,
    SystemVersionRead,
    TraceCreate,
    TraceDatasetCreate,
    TraceRead,
)
from evalops.calibration import calibrate_judge
from evalops.db import (
    AsyncJobRepository,
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    ExperimentRepository,
    JudgeCalibrationRepository,
    ProductionTraceRepository,
    ProjectRepository,
    ReleasePolicyRepository,
    SystemVersionRepository,
)
from evalops.diagnostics import diagnose_regressions
from evalops.evaluators import build_evaluators
from evalops.execution_service import execute_experiment
from evalops.gate import evaluate_gate
from evalops.judge import LLMJudge
from evalops.promotion import promote_traces_to_dataset
from evalops.runner import RunOutcome
from evalops.worker.tasks import DispatchError, enqueue_experiment_run

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
jobs = APIRouter(tags=["jobs"])
judge_calibrations = APIRouter(tags=["judge-calibrations"])
traces = APIRouter(tags=["traces"])


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
                expected_retrieval_ids=tuple(case.expected_retrieval_ids),
                expected_tool_calls=tuple(
                    domain.ExpectedToolCall(name=e.name, arguments=e.arguments)
                    for e in case.expected_tool_calls
                ),
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


@datasets.post("/projects/{project_id}/trace-datasets", status_code=status.HTTP_201_CREATED)
def create_trace_dataset(
    project_id: str, body: TraceDatasetCreate, session: SessionDep
) -> DatasetRead:
    """Promote selected production traces into a normal, replayable Dataset.

    One ``DatasetCase`` per trace id, in request order, carrying the trace's
    ``input``, its ``reference_output`` as the expected output (never its actual
    ``output``), and its id as ``source_trace_id`` (origin ``promoted_trace``).
    The production traces are read-only here -- nothing about them changes. The
    result is an ordinary ``Dataset``: feed it to the existing
    experiment / evaluation / release-gate flow, no trace-specific path.

    404 if the project or any trace id is unknown; 422 for an empty selection,
    a duplicate id, or a trace from another project; 409 if the dataset name
    already exists for this project.
    """
    dataset = promote_traces_to_dataset(
        session,
        project_id=project_id,
        trace_ids=body.trace_ids,
        name=body.name,
    )
    return DatasetRead.of(dataset)


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
    # Orchestration (load, run, persist, gate) lives in the execution service;
    # the route only adapts the HTTP request. The request-scoped session's unit
    # of work owns the transaction.
    return execute_experiment(
        session,
        experiment_id,
        body.execution.to_spec(),
        [spec.model_dump(exclude_none=True) for spec in body.evaluators],
    )


@experiments.post("/experiments/{experiment_id}/run-async", status_code=status.HTTP_202_ACCEPTED)
def run_experiment_async_route(
    experiment_id: str,
    body: RunRequest,
    session: SessionDep,
    sessions: SessionsDep,
) -> AsyncJobRead:
    """Queue a background run: validate the request, create a queued AsyncJob,
    dispatch the Celery task, and return 202 with the job.

    Structural request validation is synchronous (422); semantic/runtime
    problems (e.g. a bad evaluator config) surface later as a ``failed`` job.
    """
    _found(ExperimentRepository(session).get(experiment_id), "experiment not found")
    try:
        job = enqueue_experiment_run(
            experiment_id,
            body.execution.model_dump(),
            [spec.model_dump(exclude_none=True) for spec in body.evaluators],
            sessions=sessions,
        )
    except DispatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return AsyncJobRead.of(job)


@jobs.get("/jobs/{job_id}")
def get_job(job_id: str, session: SessionDep) -> AsyncJobRead:
    return AsyncJobRead.of(_found(AsyncJobRepository(session).get(job_id), "job not found"))


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


@experiments.get("/experiments/{experiment_id}/diagnostics")
def get_experiment_diagnostics(
    experiment_id: str, session: SessionDep
) -> RegressionDiagnosticsRead:
    """Deterministic, explanatory-only case-level regression diagnostics.

    Computed from the persisted runs / case results by :func:`diagnose_regressions`
    -- it never changes the release decision, the metrics, or the statistical
    evidence (those come from the run path and ``GET /results``). Additive and
    experiment-scoped. ``available`` is ``False`` before the first run.
    """
    experiment = _found(ExperimentRepository(session).get(experiment_id), "experiment not found")

    run_repo = EvaluationRunRepository(session)
    runs = run_repo.list_for_experiment(experiment_id)
    case_results = [
        cr for run in runs if (cr := run_repo.get_case_result_for_run(run.id)) is not None
    ]
    outcome = RunOutcome(runs=tuple(runs), case_results=tuple(case_results))
    diagnostics = diagnose_regressions(experiment, outcome)

    results = EvaluationResultRepository(session).list_for_experiment(experiment_id)
    latest_result_id = results[-1].id if results else None
    return RegressionDiagnosticsRead.of(diagnostics, evaluation_result_id=latest_result_id)


# --- LLM-judge calibration (Phase 6, CP 6.2) --------------------


@judge_calibrations.post("/judge-calibrations", status_code=status.HTTP_201_CREATED)
def create_judge_calibration(
    body: JudgeCalibrationCreate, session: SessionDep
) -> JudgeCalibrationRead:
    """Run one configured LLM judge over the supplied human-labeled examples,
    persist the agreement metrics + per-case detail, and return it.

    Calibration is pure measurement -- it does not touch release gating and
    never disables a judge. A judge/provider failure on an example is recorded
    on that case, not raised. API keys come from the environment only; a
    missing key is a 422 (``ConfigError``).
    """
    judge_spec: dict[str, Any] = {
        "type": "llm_judge",
        "provider": body.provider,
        "model": body.model,
    }
    if body.name is not None:
        judge_spec["name"] = body.name
    if body.temperature is not None:
        judge_spec["temperature"] = body.temperature
    if body.base_url is not None:
        judge_spec["base_url"] = body.base_url
    (judge,) = build_evaluators([judge_spec])
    assert isinstance(judge, LLMJudge)  # build_evaluators guarantees it for this type

    examples = [
        domain.LabeledJudgeExample(
            input=example.input,
            output=example.output,
            human_pass=example.human_pass,
            reference=example.reference,
        )
        for example in body.examples
    ]
    calibration = calibrate_judge(judge, examples)
    stored = JudgeCalibrationRepository(session).add(calibration)
    return JudgeCalibrationRead.of(stored)


@judge_calibrations.get("/judge-calibrations")
def list_judge_calibrations(session: SessionDep) -> list[JudgeCalibrationRead]:
    """Every persisted calibration, oldest first. Read-only -- no new semantics."""
    return [
        JudgeCalibrationRead.of(calibration)
        for calibration in JudgeCalibrationRepository(session).list_all()
    ]


@judge_calibrations.get("/judge-calibrations/{calibration_id}")
def get_judge_calibration(calibration_id: str, session: SessionDep) -> JudgeCalibrationRead:
    return JudgeCalibrationRead.of(
        _found(
            JudgeCalibrationRepository(session).get(calibration_id),
            "judge calibration not found",
        )
    )


# --- production traces (Phase 8, CP 8.1) -----------------------


@traces.post("/projects/{project_id}/traces", status_code=status.HTTP_201_CREATED)
def create_trace(project_id: str, body: TraceCreate, session: SessionDep) -> TraceRead:
    """Ingest one production interaction for later promotion to a regression case.

    Validates that the project and the referenced system version exist (404) and
    that the system version belongs to this project (422). Only the JSON body is
    read -- no request headers, cookies, or environment are captured, and
    ``metadata`` is stored exactly as supplied. Callers are responsible for
    sending only data they are permitted to evaluate.
    """
    _found(ProjectRepository(session).get(project_id), "project not found")
    system_version = _found(
        SystemVersionRepository(session).get(body.system_version_id),
        "system version not found",
    )
    if system_version.project_id != project_id:
        # A well-formed request that is semantically invalid -- same 422 the
        # domain-invariant handlers in ``main`` use.
        raise HTTPException(
            status_code=422, detail="system version does not belong to this project"
        )
    trace = domain.ProductionTrace(
        project_id=project_id,
        system_version_id=body.system_version_id,
        input=body.input,
        output=body.output,
        reference_output=body.reference_output,
        metadata=body.metadata,
        latency_ms=body.latency_ms,
        cost_usd=body.cost_usd,
        error=body.error,
    )
    return TraceRead.of(ProductionTraceRepository(session).add(trace))


@traces.get("/projects/{project_id}/traces")
def list_traces(project_id: str, session: SessionDep) -> list[TraceRead]:
    _found(ProjectRepository(session).get(project_id), "project not found")
    return [
        TraceRead.of(t) for t in ProductionTraceRepository(session).list_for_project(project_id)
    ]


@traces.get("/traces/{trace_id}")
def get_trace(trace_id: str, session: SessionDep) -> TraceRead:
    return TraceRead.of(_found(ProductionTraceRepository(session).get(trace_id), "trace not found"))


ROUTERS = (
    projects,
    datasets,
    system_versions,
    release_policies,
    experiments,
    jobs,
    judge_calibrations,
    traces,
)
