"""Persistence tests: domain objects round-trip through the repositories.

Fast tests run against a temp-file SQLite database with foreign keys enforced.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from evalops import domain
from evalops.db import (
    AsyncJobRepository,
    Base,
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    ExperimentRepository,
    JudgeCalibrationRepository,
    ProjectRepository,
    RecordConflict,
    RecordNotFound,
    ReleasePolicyRepository,
    SystemVersionRepository,
    create_db_engine,
    session_factory,
    unit_of_work,
)
from evalops.domain.enums import CaseOrigin, EvaluatorFamily, JobStatus, ProviderName

Sessions = sessionmaker[Session]


@pytest.fixture
def sessions(tmp_path: Path) -> Sessions:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'p.sqlite'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection: object, _: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    return session_factory(engine)


# --- domain builders ------------------------------------------------------


def _project() -> domain.Project:
    return domain.Project(name="Support QA")


def _dataset(project: domain.Project, *cases: domain.DatasetCase) -> domain.Dataset:
    cases = cases or (domain.DatasetCase(input="q", expected_output="a"),)
    return domain.Dataset(project_id=project.id, name="support", version=1, cases=cases)


def _sv(
    project: domain.Project,
    version: str = "v1",
    *,
    provider: ProviderName = ProviderName.OPENAI,
    parameters: dict[str, object] | None = None,
    rag_config: dict[str, object] | None = None,
    tool_policy: dict[str, object] | None = None,
) -> domain.SystemVersion:
    return domain.SystemVersion(
        project_id=project.id,
        name="cfg",
        version=version,
        provider=provider,
        model="m",
        prompt_template="Q: ${input}",
        parameters=parameters or {},
        rag_config=rag_config,
        tool_policy=tool_policy,
    )


class Graph(NamedTuple):
    project: domain.Project
    dataset: domain.Dataset
    baseline: domain.SystemVersion
    candidate: domain.SystemVersion
    policy: domain.ReleasePolicy
    experiment: domain.Experiment


@pytest.fixture
def graph(sessions: Sessions) -> Iterator[Graph]:
    """A fully-persisted project/dataset/versions/policy/experiment graph."""
    project = _project()
    dataset = _dataset(project)
    baseline = _sv(project, "v1")
    candidate = _sv(project, "v2")
    policy = domain.ReleasePolicy(name="default", thresholds={"latency_ms.p95": 0.2})
    experiment = domain.Experiment(
        project_id=project.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        release_policy_id=policy.id,
        repeats=2,
    )
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)
        DatasetRepository(session).add(dataset)
        SystemVersionRepository(session).add(baseline)
        SystemVersionRepository(session).add(candidate)
        ReleasePolicyRepository(session).add(policy)
        ExperimentRepository(session).add(experiment)
    yield Graph(project, dataset, baseline, candidate, policy, experiment)


# --- round trips ---------------------------------------------------------


def test_project_round_trip(sessions: Sessions) -> None:
    project = _project()
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)

    with unit_of_work(sessions) as session:
        loaded = ProjectRepository(session).get(project.id)

    assert loaded == project
    assert loaded is not None and loaded.created_at.tzinfo is not None


def test_get_missing_record_returns_none(sessions: Sessions) -> None:
    with unit_of_work(sessions) as session:
        assert ProjectRepository(session).get("does-not-exist") is None
        assert EvaluationRunRepository(session).get("nope") is None


def test_list_all_projects(sessions: Sessions) -> None:
    a, b = domain.Project(name="A"), domain.Project(name="B")
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(a)
        ProjectRepository(session).add(b)

    with unit_of_work(sessions) as session:
        ids = {p.id for p in ProjectRepository(session).list_all()}

    assert ids == {a.id, b.id}


def test_dataset_round_trip_preserves_case_order_and_fields(sessions: Sessions) -> None:
    project = _project()
    cases = (
        domain.DatasetCase(input="c0", expected_output="0"),
        domain.DatasetCase(input="c1", expected_output=None),
        domain.DatasetCase(input="c2", origin=CaseOrigin.PROMOTED_TRACE, source_trace_id="trace-9"),
    )
    dataset = _dataset(project, *cases)
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)
        DatasetRepository(session).add(dataset)

    with unit_of_work(sessions) as session:
        loaded = DatasetRepository(session).get(dataset.id)

    assert loaded is not None
    assert [c.input for c in loaded.cases] == ["c0", "c1", "c2"]
    assert loaded.cases[1].expected_output is None
    assert loaded.cases[2].origin is CaseOrigin.PROMOTED_TRACE
    assert loaded.cases[2].source_trace_id == "trace-9"
    assert loaded == dataset


def test_dataset_list_for_project(sessions: Sessions, graph: Graph) -> None:
    with unit_of_work(sessions) as session:
        datasets = DatasetRepository(session).list_for_project(graph.project.id)

    assert [d.id for d in datasets] == [graph.dataset.id]


def test_system_version_round_trip_preserves_json_enum_and_optionals(sessions: Sessions) -> None:
    project = _project()
    version = _sv(
        project,
        provider=ProviderName.ANTHROPIC,
        parameters={"temperature": 0.2, "stop": ["\n"]},
        rag_config={"top_k": 5},
        tool_policy=None,
    )
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)
        SystemVersionRepository(session).add(version)

    with unit_of_work(sessions) as session:
        loaded = SystemVersionRepository(session).get(version.id)

    assert loaded is not None
    assert loaded.provider is ProviderName.ANTHROPIC
    assert dict(loaded.parameters) == {"temperature": 0.2, "stop": ["\n"]}
    assert loaded.rag_config == {"top_k": 5}
    assert loaded.tool_policy is None
    with pytest.raises(TypeError):  # parameters comes back read-only
        loaded.parameters["temperature"] = 0.0  # type: ignore[index]


def test_release_policy_round_trip(sessions: Sessions) -> None:
    policy = domain.ReleasePolicy(
        name="strict",
        thresholds={"success_rate": 0.0, "cost_usd.total": 0.1},
        max_safety_violations=2,
    )
    with unit_of_work(sessions) as session:
        ReleasePolicyRepository(session).add(policy)

    with unit_of_work(sessions) as session:
        loaded = ReleasePolicyRepository(session).get(policy.id)

    assert loaded == policy
    assert loaded is not None and dict(loaded.thresholds) == dict(policy.thresholds)


def _calibration_case(
    *, human: bool, judge: bool | None, error: str | None = None
) -> domain.JudgeCalibrationCase:
    return domain.JudgeCalibrationCase(
        input="what is 2+2?",
        output="4",
        reference="4" if judge is not None else None,
        human_pass=human,
        judge_pass=judge,
        judge_score=None if judge is None else (0.95 if judge else 0.05),
        judge_reasoning=None if judge is None else "matches the reference",
        error=error,
    )


def test_judge_calibration_round_trip(sessions: Sessions) -> None:
    cases = (
        _calibration_case(human=True, judge=True),
        _calibration_case(human=False, judge=False),
        _calibration_case(human=True, judge=False),
        _calibration_case(human=True, judge=None, error="ProviderError: unreachable"),
    )
    calibration = domain.JudgeCalibration(
        judge_provider=ProviderName.ANTHROPIC,
        judge_model="claude-3-5-haiku",
        judge_name="correctness",
        judge_temperature=0.0,
        rubric_id="judge-v1",
        metrics=domain.JudgeCalibrationMetrics(
            total=4,
            scored=3,
            failures=1,
            agreements=2,
            agreement_rate=2 / 3,
            true_positives=1,
            true_negatives=1,
            false_positives=0,
            false_negatives=1,
            precision=1.0,
            recall=0.5,
            f1=None,
        ),
        cases=cases,
    )

    with unit_of_work(sessions) as session:
        JudgeCalibrationRepository(session).add(calibration)

    with unit_of_work(sessions) as session:
        loaded = JudgeCalibrationRepository(session).get(calibration.id)
        listed = JudgeCalibrationRepository(session).list_all()

    assert loaded == calibration  # full structural equality: metrics + ordered cases
    assert [c.id for c in listed] == [calibration.id]
    assert loaded is not None
    assert loaded.metrics.f1 is None and loaded.metrics.agreement_rate == 2 / 3
    assert loaded.cases[3].judge_pass is None and "unreachable" in (loaded.cases[3].error or "")
    assert loaded.cases[0].judge_reasoning == "matches the reference"


def test_missing_judge_calibration_is_none(sessions: Sessions) -> None:
    with unit_of_work(sessions) as session:
        assert JudgeCalibrationRepository(session).get("nope") is None


def test_experiment_round_trip_with_and_without_policy(sessions: Sessions) -> None:
    project = _project()
    dataset = _dataset(project)
    baseline, candidate = _sv(project, "v1"), _sv(project, "v2")
    with_policy = domain.ReleasePolicy(name="p", thresholds={})
    exp_with = domain.Experiment(
        project_id=project.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
        release_policy_id=with_policy.id,
    )
    exp_without = domain.Experiment(
        project_id=project.id,
        dataset_id=dataset.id,
        baseline_version_id=baseline.id,
        candidate_version_id=candidate.id,
    )
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)
        DatasetRepository(session).add(dataset)
        SystemVersionRepository(session).add(baseline)
        SystemVersionRepository(session).add(candidate)
        ReleasePolicyRepository(session).add(with_policy)
        ExperimentRepository(session).add(exp_with)
        ExperimentRepository(session).add(exp_without)

    with unit_of_work(sessions) as session:
        repo = ExperimentRepository(session)
        assert repo.get(exp_with.id) == exp_with
        assert repo.get(exp_without.id) == exp_without
        assert repo.get(exp_without.id).release_policy_id is None  # type: ignore[union-attr]


def test_evaluation_run_round_trip_preserves_usage(sessions: Sessions, graph: Graph) -> None:
    exp = graph.experiment
    baseline = graph.baseline
    case = graph.dataset.cases[0]

    ok = domain.EvaluationRun(
        experiment_id=exp.id,
        system_version_id=baseline.id,
        case_id=case.id,
        repeat_index=0,
        output="4",
        usage=domain.UsageMetrics(
            prompt_tokens=5, completion_tokens=3, cost_usd=0.01, latency_ms=12.5
        ),
    )
    failed = domain.EvaluationRun(
        experiment_id=exp.id,
        system_version_id=baseline.id,
        case_id=case.id,
        repeat_index=1,
        output="",
        error="provider timeout",
    )
    with unit_of_work(sessions) as session:
        EvaluationRunRepository(session).add(ok)
        EvaluationRunRepository(session).add(failed)

    with unit_of_work(sessions) as session:
        repo = EvaluationRunRepository(session)
        loaded_ok = repo.get(ok.id)
        loaded_failed = repo.get(failed.id)
        for_exp = {r.id for r in repo.list_for_experiment(exp.id)}

    assert loaded_ok == ok
    assert loaded_ok is not None and loaded_ok.usage.total_tokens == 8
    assert loaded_failed == failed
    assert loaded_failed is not None and loaded_failed.error == "provider timeout"
    assert for_exp == {ok.id, failed.id}


def test_case_result_round_trip_preserves_scores(sessions: Sessions, graph: Graph) -> None:
    exp = graph.experiment
    baseline = graph.baseline
    case = graph.dataset.cases[0]

    run = domain.EvaluationRun(
        experiment_id=exp.id,
        system_version_id=baseline.id,
        case_id=case.id,
        repeat_index=0,
        output="4",
    )
    case_result = domain.CaseResult(
        run_id=run.id,
        scores=(
            domain.EvaluatorScore(
                evaluator="exact_match",
                family=EvaluatorFamily.DETERMINISTIC,
                score=1.0,
                passed=True,
            ),
            domain.EvaluatorScore(
                evaluator="similarity", family=EvaluatorFamily.STATISTICAL, score=0.8, passed=None
            ),
        ),
    )
    with unit_of_work(sessions) as session:
        repo = EvaluationRunRepository(session)
        repo.add(run)
        repo.add_case_result(case_result)

    with unit_of_work(sessions) as session:
        loaded = EvaluationRunRepository(session).get_case_result_for_run(run.id)

    assert loaded == case_result
    assert loaded is not None
    assert [s.evaluator for s in loaded.scores] == ["exact_match", "similarity"]
    assert loaded.scores[1].family is EvaluatorFamily.STATISTICAL
    assert loaded.scores[1].passed is None


def test_evaluation_result_round_trip_preserves_metric_order(
    sessions: Sessions, graph: Graph
) -> None:
    exp = graph.experiment
    result = domain.EvaluationResult(
        experiment_id=exp.id,
        metrics=(
            domain.MetricComparison(metric="success_rate", baseline_value=1.0, candidate_value=1.0),
            domain.MetricComparison(
                metric="latency_ms.p95", baseline_value=40.0, candidate_value=60.0
            ),
        ),
    )
    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(result)

    with unit_of_work(sessions) as session:
        repo = EvaluationResultRepository(session)
        loaded = repo.get(result.id)
        for_exp = repo.list_for_experiment(exp.id)

    assert loaded == result
    assert loaded is not None
    assert [m.metric for m in loaded.metrics] == ["success_rate", "latency_ms.p95"]
    assert loaded.metrics[1].delta == 20.0
    assert [r.id for r in for_exp] == [result.id]


def test_evaluation_result_round_trip_preserves_statistical_evidence(
    sessions: Sessions, graph: Graph
) -> None:
    """CP 5.2: MetricEvidence (incl. None CIs and the three SampleSummary
    sub-objects) reconstructs faithfully, in order, from its own child table."""

    def _summary(n: int, mean: float, stdev: float) -> domain.SampleSummary:
        return domain.SampleSummary(n=n, mean=mean, median=mean, stdev=stdev)

    supported = domain.MetricEvidence(
        metric="success_rate",
        kind="binary",
        n_pairs=10,
        baseline=_summary(10, 1.0, 0.0),
        candidate=_summary(10, 0.6, 0.49),
        paired_delta=_summary(10, -0.4, 0.51),
        delta=-0.4,
        relative_change=-0.4,
        confidence_level=0.95,
        ci_low=-0.55,
        ci_high=-0.25,
        ci_excludes_zero=True,
        insufficient_evidence=False,
        method="paired_bootstrap_percentile",
        resamples=2000,
        seed=0x5EED0501,
        dropped_provider_failures=1,
    )
    low_evidence = domain.MetricEvidence(
        metric="contains.pass_rate",
        kind="binary",
        n_pairs=2,
        baseline=_summary(2, 1.0, 0.0),
        candidate=_summary(2, 1.0, 0.0),
        paired_delta=_summary(2, 0.0, 0.0),
        delta=0.0,
        relative_change=0.0,
        confidence_level=0.95,
        ci_low=None,
        ci_high=None,
        ci_excludes_zero=False,
        insufficient_evidence=True,
        method="paired_bootstrap_percentile",
        resamples=2000,
        seed=0x5EED0502,
    )
    result = domain.EvaluationResult(
        experiment_id=graph.experiment.id,
        metrics=(
            domain.MetricComparison(metric="success_rate", baseline_value=1.0, candidate_value=0.6),
            domain.MetricComparison(
                metric="contains.pass_rate", baseline_value=1.0, candidate_value=1.0
            ),
        ),
        evidence=(supported, low_evidence),
    )

    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(result)

    with unit_of_work(sessions) as session:
        loaded = EvaluationResultRepository(session).get(result.id)

    assert loaded is not None
    assert loaded == result  # full structural equality, evidence included
    assert [e.metric for e in loaded.evidence] == ["success_rate", "contains.pass_rate"]
    assert loaded.evidence[0].ci_low == -0.55 and loaded.evidence[0].dropped_provider_failures == 1
    assert loaded.evidence[1].ci_low is None and loaded.evidence[1].insufficient_evidence is True


def test_evaluation_result_without_evidence_still_round_trips(
    sessions: Sessions, graph: Graph
) -> None:
    """Backward compatibility: a pre-Phase-5 result (no evidence) is unchanged."""
    result = domain.EvaluationResult(
        experiment_id=graph.experiment.id,
        metrics=(
            domain.MetricComparison(metric="success_rate", baseline_value=1.0, candidate_value=1.0),
        ),
    )
    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(result)
    with unit_of_work(sessions) as session:
        loaded = EvaluationResultRepository(session).get(result.id)

    assert loaded == result
    assert loaded is not None and loaded.evidence == ()


# --- conflict & rollback behaviour ------------------------------------


def test_duplicate_id_raises_record_conflict(sessions: Sessions) -> None:
    project = _project()
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)

    with pytest.raises(RecordConflict, match="Project"), unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)


def test_duplicate_dataset_name_and_version_raises_record_conflict(sessions: Sessions) -> None:
    project = _project()
    first = domain.Dataset(
        project_id=project.id,
        name="support",
        version=1,
        cases=(domain.DatasetCase(input="q", expected_output="a"),),
    )
    clash = domain.Dataset(
        project_id=project.id,
        name="support",
        version=1,
        cases=(domain.DatasetCase(input="q2", expected_output="b"),),
    )
    with pytest.raises(RecordConflict), unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)
        DatasetRepository(session).add(first)
        DatasetRepository(session).add(clash)


def test_foreign_key_violation_raises_record_conflict(sessions: Sessions) -> None:
    orphan = _dataset(_project())  # project never persisted
    with pytest.raises(RecordConflict), unit_of_work(sessions) as session:
        DatasetRepository(session).add(orphan)


def test_unit_of_work_rolls_back_the_whole_transaction_on_failure(sessions: Sessions) -> None:
    good = domain.Project(name="Good")
    with pytest.raises(RecordConflict), unit_of_work(sessions) as session:
        ProjectRepository(session).add(good)
        ProjectRepository(session).add(good)  # duplicate id -> conflict

    with unit_of_work(sessions) as session:
        assert ProjectRepository(session).get(good.id) is None


def test_unit_of_work_commits_on_success(sessions: Sessions) -> None:
    project = _project()
    with unit_of_work(sessions) as session:
        ProjectRepository(session).add(project)

    with unit_of_work(sessions) as session:
        assert ProjectRepository(session).get(project.id) == project


def test_repository_add_does_not_commit(sessions: Sessions) -> None:
    project = _project()
    session = sessions()
    try:
        ProjectRepository(session).add(project)  # flushes, no commit
        session.rollback()
        assert ProjectRepository(session).get(project.id) is None
    finally:
        session.close()


# --- AsyncJob lifecycle -------------------------------------------------


def test_async_job_round_trip(sessions: Sessions, graph: Graph) -> None:
    job = domain.AsyncJob(experiment_id=graph.experiment.id)
    with unit_of_work(sessions) as session:
        AsyncJobRepository(session).add(job)

    with unit_of_work(sessions) as session:
        loaded = AsyncJobRepository(session).get(job.id)

    assert loaded == job
    assert loaded is not None
    assert loaded.status is JobStatus.QUEUED
    assert loaded.created_at.tzinfo is not None
    assert (loaded.started_at, loaded.completed_at, loaded.error) == (None, None, None)


def test_async_job_queued_running_completed(sessions: Sessions, graph: Graph) -> None:
    result = domain.EvaluationResult(experiment_id=graph.experiment.id, metrics=())
    job = domain.AsyncJob(experiment_id=graph.experiment.id)
    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(result)
        AsyncJobRepository(session).add(job)

    with unit_of_work(sessions) as session:
        running = AsyncJobRepository(session).mark_running(job.id, celery_task_id="t-1")
    assert running.status is JobStatus.RUNNING
    assert running.started_at is not None and running.celery_task_id == "t-1"

    with unit_of_work(sessions) as session:
        done = AsyncJobRepository(session).mark_completed(job.id, result.id)
    assert done.status is JobStatus.COMPLETED
    assert done.evaluation_result_id == result.id
    assert done.error is None
    assert done.completed_at is not None
    assert done.created_at <= done.started_at <= done.completed_at  # type: ignore[operator]


def test_async_job_failed_bounds_error_and_allows_queued_source(
    sessions: Sessions, graph: Graph
) -> None:
    a = domain.AsyncJob(experiment_id=graph.experiment.id)
    b = domain.AsyncJob(experiment_id=graph.experiment.id)
    with unit_of_work(sessions) as session:
        AsyncJobRepository(session).add(a)
        AsyncJobRepository(session).add(b)

    # running -> failed, with an over-long message
    with unit_of_work(sessions) as session:
        jobs = AsyncJobRepository(session)
        jobs.mark_running(a.id)
        failed = jobs.mark_failed(a.id, "boom " * 2000)
    assert failed.status is JobStatus.FAILED
    assert failed.evaluation_result_id is None
    assert failed.error is not None and len(failed.error) <= 2000
    assert failed.completed_at is not None

    # queued -> failed is allowed (never started)
    with unit_of_work(sessions) as session:
        from_queued = AsyncJobRepository(session).mark_failed(b.id, "rejected before start")
    assert from_queued.status is JobStatus.FAILED
    assert from_queued.started_at is None


def test_async_job_illegal_transitions_and_missing_id(sessions: Sessions, graph: Graph) -> None:
    result = domain.EvaluationResult(experiment_id=graph.experiment.id, metrics=())
    job = domain.AsyncJob(experiment_id=graph.experiment.id)
    with unit_of_work(sessions) as session:
        EvaluationResultRepository(session).add(result)
        AsyncJobRepository(session).add(job)

    with unit_of_work(sessions) as session:
        assert AsyncJobRepository(session).get("nope") is None
        with pytest.raises(RecordNotFound):
            AsyncJobRepository(session).mark_running("nope")

    with (
        unit_of_work(sessions) as session,
        pytest.raises(RecordConflict),  # can't complete a queued job
    ):
        AsyncJobRepository(session).mark_completed(job.id, result.id)

    with unit_of_work(sessions) as session:
        jobs = AsyncJobRepository(session)
        jobs.mark_running(job.id)
        with pytest.raises(RecordConflict):  # can't start twice
            jobs.mark_running(job.id)

    with unit_of_work(sessions) as session:
        jobs = AsyncJobRepository(session)
        jobs.mark_completed(job.id, result.id)
        with pytest.raises(RecordConflict):  # terminal
            jobs.mark_failed(job.id, "too late")


def test_async_job_domain_invariants() -> None:
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(domain.DomainValidationError):
        domain.AsyncJob(experiment_id="e", status=JobStatus.RUNNING)  # no started_at
    with pytest.raises(domain.DomainValidationError):
        domain.AsyncJob(  # completed without a result
            experiment_id="e",
            status=JobStatus.COMPLETED,
            created_at=moment,
            started_at=moment,
            completed_at=moment,
        )
    with pytest.raises(domain.DomainValidationError):
        domain.AsyncJob(  # failed without an error message
            experiment_id="e",
            status=JobStatus.FAILED,
            created_at=moment,
            completed_at=moment,
        )
