"""Repositories: save and load domain aggregates through a SQLAlchemy session.

Each repository takes an open :class:`~sqlalchemy.orm.Session` and never
commits -- wrap calls in :func:`evalops.db.session.unit_of_work`. ``get``
returns ``None`` for a missing record; ``add`` raises
:class:`~evalops.db.errors.RecordConflict` on a uniqueness or foreign-key
violation (which also marks the surrounding transaction for rollback).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evalops import domain
from evalops.db import mapping
from evalops.db import models as orm
from evalops.db.errors import RecordConflict, RecordNotFound
from evalops.domain._time import utcnow
from evalops.domain.enums import JobStatus

#: Cap on stored failure text -- keep the row small and bounded.
_MAX_ERROR_LEN = 2000


def _flush(session: Session, entity: str) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        raise RecordConflict(f"{entity} conflicts with an existing record: {exc.orig}") from exc


def _add(session: Session, row: object, entity: str) -> None:
    session.add(row)
    _flush(session, entity)


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, project: domain.Project) -> domain.Project:
        _add(self._session, mapping.project_to_orm(project), "Project")
        return project

    def get(self, project_id: str) -> domain.Project | None:
        row = self._session.get(orm.Project, project_id)
        return None if row is None else mapping.project_from_orm(row)

    def list_all(self) -> list[domain.Project]:
        rows = self._session.scalars(
            select(orm.Project).order_by(orm.Project.created_at, orm.Project.id)
        )
        return [mapping.project_from_orm(row) for row in rows]


class DatasetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, dataset: domain.Dataset) -> domain.Dataset:
        _add(self._session, mapping.dataset_to_orm(dataset), "Dataset")
        return dataset

    def get(self, dataset_id: str) -> domain.Dataset | None:
        row = self._session.get(orm.Dataset, dataset_id)
        return None if row is None else mapping.dataset_from_orm(row)

    def list_for_project(self, project_id: str) -> list[domain.Dataset]:
        rows = self._session.scalars(
            select(orm.Dataset)
            .where(orm.Dataset.project_id == project_id)
            .order_by(orm.Dataset.name, orm.Dataset.version)
        )
        return [mapping.dataset_from_orm(row) for row in rows]


class SystemVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, system_version: domain.SystemVersion) -> domain.SystemVersion:
        _add(self._session, mapping.system_version_to_orm(system_version), "SystemVersion")
        return system_version

    def get(self, system_version_id: str) -> domain.SystemVersion | None:
        row = self._session.get(orm.SystemVersion, system_version_id)
        return None if row is None else mapping.system_version_from_orm(row)

    def list_for_project(self, project_id: str) -> list[domain.SystemVersion]:
        rows = self._session.scalars(
            select(orm.SystemVersion)
            .where(orm.SystemVersion.project_id == project_id)
            .order_by(orm.SystemVersion.name, orm.SystemVersion.version)
        )
        return [mapping.system_version_from_orm(row) for row in rows]


class ReleasePolicyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, policy: domain.ReleasePolicy) -> domain.ReleasePolicy:
        _add(self._session, mapping.release_policy_to_orm(policy), "ReleasePolicy")
        return policy

    def get(self, policy_id: str) -> domain.ReleasePolicy | None:
        row = self._session.get(orm.ReleasePolicy, policy_id)
        return None if row is None else mapping.release_policy_from_orm(row)

    def list_all(self) -> list[domain.ReleasePolicy]:
        rows = self._session.scalars(select(orm.ReleasePolicy).order_by(orm.ReleasePolicy.name))
        return [mapping.release_policy_from_orm(row) for row in rows]


class ExperimentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, experiment: domain.Experiment) -> domain.Experiment:
        _add(self._session, mapping.experiment_to_orm(experiment), "Experiment")
        return experiment

    def get(self, experiment_id: str) -> domain.Experiment | None:
        row = self._session.get(orm.Experiment, experiment_id)
        return None if row is None else mapping.experiment_from_orm(row)

    def list_for_project(self, project_id: str) -> list[domain.Experiment]:
        rows = self._session.scalars(
            select(orm.Experiment)
            .where(orm.Experiment.project_id == project_id)
            .order_by(orm.Experiment.created_at, orm.Experiment.id)
        )
        return [mapping.experiment_from_orm(row) for row in rows]


class EvaluationRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: domain.EvaluationRun) -> domain.EvaluationRun:
        _add(self._session, mapping.evaluation_run_to_orm(run), "EvaluationRun")
        return run

    def get(self, run_id: str) -> domain.EvaluationRun | None:
        row = self._session.get(orm.EvaluationRun, run_id)
        return None if row is None else mapping.evaluation_run_from_orm(row)

    def list_for_experiment(self, experiment_id: str) -> list[domain.EvaluationRun]:
        rows = self._session.scalars(
            select(orm.EvaluationRun)
            .where(orm.EvaluationRun.experiment_id == experiment_id)
            .order_by(orm.EvaluationRun.created_at, orm.EvaluationRun.id)
        )
        return [mapping.evaluation_run_from_orm(row) for row in rows]

    def add_case_result(self, case_result: domain.CaseResult) -> domain.CaseResult:
        _add(self._session, mapping.case_result_to_orm(case_result), "CaseResult")
        return case_result

    def get_case_result_for_run(self, run_id: str) -> domain.CaseResult | None:
        row = self._session.scalars(
            select(orm.CaseResult).where(orm.CaseResult.run_id == run_id)
        ).one_or_none()
        return None if row is None else mapping.case_result_from_orm(row)


class EvaluationResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: domain.EvaluationResult) -> domain.EvaluationResult:
        _add(self._session, mapping.evaluation_result_to_orm(result), "EvaluationResult")
        return result

    def get(self, result_id: str) -> domain.EvaluationResult | None:
        row = self._session.get(orm.EvaluationResult, result_id)
        return None if row is None else mapping.evaluation_result_from_orm(row)

    def list_for_experiment(self, experiment_id: str) -> list[domain.EvaluationResult]:
        rows = self._session.scalars(
            select(orm.EvaluationResult)
            .where(orm.EvaluationResult.experiment_id == experiment_id)
            .order_by(orm.EvaluationResult.created_at, orm.EvaluationResult.id)
        )
        return [mapping.evaluation_result_from_orm(row) for row in rows]


def _bound_error(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) > _MAX_ERROR_LEN:
        cleaned = cleaned[: _MAX_ERROR_LEN - 1] + "…"
    return cleaned or "unknown error"


class AsyncJobRepository:
    """The durable lifecycle of a background experiment run.

    ``add`` inserts a queued job. Each ``mark_*`` performs one targeted state
    transition and flushes (never commits) -- the caller's unit of work owns
    the transaction. Illegal transitions raise :class:`RecordConflict`; an
    unknown job id raises :class:`RecordNotFound`.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, job: domain.AsyncJob) -> domain.AsyncJob:
        _add(self._session, mapping.async_job_to_orm(job), "AsyncJob")
        return job

    def get(self, job_id: str) -> domain.AsyncJob | None:
        row = self._session.get(orm.AsyncJob, job_id)
        return None if row is None else mapping.async_job_from_orm(row)

    def _row(self, job_id: str) -> orm.AsyncJob:
        row = self._session.get(orm.AsyncJob, job_id)
        if row is None:
            raise RecordNotFound(f"async job {job_id!r} not found")
        return row

    def mark_running(
        self, job_id: str, *, celery_task_id: str | None = None, at: datetime | None = None
    ) -> domain.AsyncJob:
        row = self._row(job_id)
        if row.status is not JobStatus.QUEUED:
            raise RecordConflict(
                f"async job {job_id!r} is {row.status.value}; only a queued job can start"
            )
        row.status = JobStatus.RUNNING
        row.started_at = at or utcnow()
        if celery_task_id is not None:
            row.celery_task_id = celery_task_id
        _flush(self._session, "AsyncJob")
        return mapping.async_job_from_orm(row)

    def mark_completed(
        self, job_id: str, evaluation_result_id: str, *, at: datetime | None = None
    ) -> domain.AsyncJob:
        row = self._row(job_id)
        if row.status is not JobStatus.RUNNING:
            raise RecordConflict(
                f"async job {job_id!r} is {row.status.value}; only a running job can complete"
            )
        row.status = JobStatus.COMPLETED
        row.evaluation_result_id = evaluation_result_id
        row.error = None
        row.completed_at = at or utcnow()
        _flush(self._session, "AsyncJob")
        return mapping.async_job_from_orm(row)

    def mark_failed(
        self, job_id: str, error: str, *, at: datetime | None = None
    ) -> domain.AsyncJob:
        row = self._row(job_id)
        if row.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            raise RecordConflict(f"async job {job_id!r} is already {row.status.value} (terminal)")
        row.status = JobStatus.FAILED
        row.error = _bound_error(error)
        row.evaluation_result_id = None
        row.completed_at = at or utcnow()
        _flush(self._session, "AsyncJob")
        return mapping.async_job_from_orm(row)
