"""Persistence layer: SQLAlchemy ORM schema and engine configuration.

Schema and infrastructure only -- no repositories or business logic yet.
"""

from evalops.db.base import Base
from evalops.db.engine import DEFAULT_DATABASE_URL, create_db_engine, database_url
from evalops.db.models import (
    CaseResult,
    Dataset,
    DatasetCase,
    EvaluationResult,
    EvaluationRun,
    EvaluatorScore,
    Experiment,
    MetricComparison,
    Project,
    ReleasePolicy,
    SystemVersion,
)

__all__ = [
    "DEFAULT_DATABASE_URL",
    "Base",
    "CaseResult",
    "Dataset",
    "DatasetCase",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluatorScore",
    "Experiment",
    "MetricComparison",
    "Project",
    "ReleasePolicy",
    "SystemVersion",
    "create_db_engine",
    "database_url",
]
