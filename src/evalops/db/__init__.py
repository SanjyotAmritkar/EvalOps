"""Persistence layer: SQLAlchemy ORM schema, session management, and repositories.

The ORM models mirror the frozen domain entities but stay separate from them;
:mod:`evalops.db.mapping` is the only place the two meet. No FastAPI, no
workers, no changes to the evaluation engine.
"""

from evalops.db.base import Base
from evalops.db.engine import DEFAULT_DATABASE_URL, create_db_engine, database_url
from evalops.db.errors import PersistenceError, RecordConflict, RecordNotFound
from evalops.db.models import (
    AsyncJob,
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationResult,
    EvaluationRun,
    EvaluatorScore,
    Experiment,
    JudgeCalibration,
    JudgeCalibrationCase,
    MetricComparison,
    MetricEvidence,
    Project,
    ReleasePolicy,
    SystemVersion,
)
from evalops.db.repositories import (
    AsyncJobRepository,
    DatasetRepository,
    EvaluationResultRepository,
    EvaluationRunRepository,
    ExperimentRepository,
    JudgeCalibrationRepository,
    ProjectRepository,
    ReleasePolicyRepository,
    SystemVersionRepository,
)
from evalops.db.session import session_factory, unit_of_work

__all__ = [
    "DEFAULT_DATABASE_URL",
    "AsyncJob",
    "AsyncJobRepository",
    "Base",
    "CaseResult",
    "Dataset",
    "DatasetCase",
    "DatasetRepository",
    "EvaluationResult",
    "EvaluationResultRepository",
    "EvaluationRun",
    "EvaluationRunRepository",
    "EvaluatorScore",
    "Experiment",
    "ExperimentRepository",
    "JudgeCalibration",
    "JudgeCalibrationCase",
    "JudgeCalibrationRepository",
    "MetricComparison",
    "MetricEvidence",
    "PersistenceError",
    "Project",
    "ProjectRepository",
    "RecordConflict",
    "RecordNotFound",
    "ReleasePolicy",
    "ReleasePolicyRepository",
    "SystemVersion",
    "SystemVersionRepository",
    "create_db_engine",
    "database_url",
    "session_factory",
    "unit_of_work",
]
