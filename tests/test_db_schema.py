"""Schema tests for evalops.db -- structure, mappings, and the initial migration.

Everything here runs against an in-memory / temp-file SQLite database; no
external PostgreSQL server is required. Production uses PostgreSQL (JSONB); the
SQLite variant of the JSON columns is exercised here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    CheckConstraint,
    Engine,
    ForeignKey,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Session

from evalops.db import (
    Base,
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
    database_url,
)
from evalops.db.engine import DEFAULT_DATABASE_URL
from evalops.domain.enums import CaseOrigin, EvaluatorFamily, ProviderName
from evalops.domain.ids import new_id

_EXPECTED_TABLES = {
    "project",
    "dataset",
    "dataset_case",
    "system_version",
    "experiment",
    "release_policy",
    "evaluation_run",
    "case_result",
    "evaluator_score",
    "evaluation_result",
    "metric_comparison",
    "metric_evidence",
    "async_job",
    "judge_calibration",
    "judge_calibration_case",
    "production_trace",
}


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return eng


def _unique_column_sets(table: Table) -> set[tuple[str, ...]]:
    return {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


# --- metadata structure ----------------------------------------------------


def test_all_domain_concepts_have_a_table() -> None:
    assert set(Base.metadata.tables) == _EXPECTED_TABLES


def test_create_all_succeeds_on_sqlite(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) == _EXPECTED_TABLES


def test_project_owns_datasets_system_versions_and_experiments() -> None:
    for child in ("dataset", "system_version", "experiment"):
        fks = Base.metadata.tables[child].foreign_keys
        assert any(fk.column.table.name == "project" for fk in fks), child


def test_dataset_case_belongs_to_a_dataset_and_orders_by_position() -> None:
    table = Base.metadata.tables["dataset_case"]
    assert {fk.column.table.name for fk in table.foreign_keys} == {"dataset"}
    assert "position" in table.c
    assert ("dataset_id", "position") in _unique_column_sets(table)


def test_evaluation_run_is_unique_per_experiment_version_case_and_repeat() -> None:
    table = Base.metadata.tables["evaluation_run"]
    assert ("experiment_id", "system_version_id", "case_id", "repeat_index") in _unique_column_sets(
        table
    )


def test_case_result_is_one_to_one_with_run() -> None:
    assert ("run_id",) in _unique_column_sets(Base.metadata.tables["case_result"])


def test_value_object_children_use_composite_natural_keys() -> None:
    assert [c.name for c in Base.metadata.tables["evaluator_score"].primary_key.columns] == [
        "case_result_id",
        "evaluator",
    ]
    assert [c.name for c in Base.metadata.tables["metric_comparison"].primary_key.columns] == [
        "evaluation_result_id",
        "metric",
    ]


def test_usage_metrics_are_flattened_onto_evaluation_run() -> None:
    cols = Base.metadata.tables["evaluation_run"].c
    for name in ("prompt_tokens", "completion_tokens", "cost_usd", "latency_ms", "output", "error"):
        assert name in cols


def test_mapping_fields_are_json_columns() -> None:
    for table, column in (
        ("system_version", "parameters"),
        ("system_version", "rag_config"),
        ("system_version", "tool_policy"),
        ("release_policy", "thresholds"),
    ):
        assert Base.metadata.tables[table].c[column].type.__class__.__name__ == "JSON"


def test_enum_columns_store_domain_wire_values() -> None:
    provider = Base.metadata.tables["system_version"].c.provider.type
    family = Base.metadata.tables["evaluator_score"].c.family.type
    assert isinstance(provider, SAEnum)
    assert isinstance(family, SAEnum)
    assert set(provider.enums) == {p.value for p in ProviderName}
    assert set(family.enums) == {f.value for f in EvaluatorFamily}


def test_domain_invariants_are_encoded_as_check_constraints() -> None:
    def checks(table: str) -> set[str]:
        return {
            str(c.name)
            for c in Base.metadata.tables[table].constraints
            if isinstance(c, CheckConstraint)
        }

    assert "ck_dataset_version_positive" in checks("dataset")
    assert "ck_experiment_repeats_positive" in checks("experiment")
    assert "ck_experiment_baseline_ne_candidate" in checks("experiment")
    assert "ck_evaluator_score_score_unit_interval" in checks("evaluator_score")
    assert "ck_release_policy_max_safety_violations_nonneg" in checks("release_policy")


def test_foreign_keys_cascade_on_delete() -> None:
    for fk in Base.metadata.tables["dataset_case"].foreign_keys:
        assert fk.ondelete == "CASCADE"
    release_fk = next(iter(Base.metadata.tables["experiment"].c.release_policy_id.foreign_keys))
    assert release_fk.ondelete == "SET NULL"


def test_production_trace_references_project_and_version_and_indexes_recency() -> None:
    table = Base.metadata.tables["production_trace"]
    assert {fk.column.table.name for fk in table.foreign_keys} == {"project", "system_version"}
    for fk in table.foreign_keys:
        assert fk.ondelete == "CASCADE"
    # per-project, per-version, and recency reads are all indexed
    for column in ("project_id", "system_version_id", "created_at"):
        assert table.c[column].index is True
    checks = {str(c.name) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {
        "ck_production_trace_latency_ms_nonneg",
        "ck_production_trace_cost_usd_nonneg",
    }
    # caller context is a JSON column, never scraped fields
    assert table.c["trace_metadata"].type.__class__.__name__ == "JSON"


# --- a full-graph round trip ------------------------------------------------


def test_full_object_graph_persists_and_reloads(engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        project = Project(id=new_id(), name="Support QA", created_at=now)
        dataset = Dataset(id=new_id(), name="support", version=1, created_at=now, project=project)
        case0 = DatasetCase(
            id=new_id(),
            position=0,
            input="2+2?",
            expected_output="4",
            origin=CaseOrigin.AUTHORED,
            dataset=dataset,
        )
        baseline = SystemVersion(
            id=new_id(),
            name="cfg",
            version="v1",
            provider=ProviderName.OLLAMA,
            model="llama3.2",
            prompt_template="Q: ${input}",
            parameters={"temperature": 0.0},
            created_at=now,
            project=project,
        )
        candidate = SystemVersion(
            id=new_id(),
            name="cfg",
            version="v2",
            provider=ProviderName.OLLAMA,
            model="llama3.2",
            prompt_template="Q: ${input}",
            parameters={},
            created_at=now,
            project=project,
        )
        policy = ReleasePolicy(
            id=new_id(), name="default", thresholds={"latency_ms.p95": 0.2}, max_safety_violations=0
        )
        experiment = Experiment(
            id=new_id(),
            repeats=2,
            created_at=now,
            project=project,
            dataset=dataset,
            baseline_version=baseline,
            candidate_version=candidate,
            release_policy=policy,
        )
        run = EvaluationRun(
            id=new_id(),
            experiment=experiment,
            system_version_id=baseline.id,
            case_id=case0.id,
            repeat_index=0,
            output="4",
            prompt_tokens=3,
            completion_tokens=1,
            cost_usd=0.0,
            latency_ms=12.5,
            created_at=now,
        )
        result = CaseResult(id=new_id(), run=run, created_at=now)
        result.scores.append(
            EvaluatorScore(
                evaluator="exact_match",
                position=0,
                family=EvaluatorFamily.DETERMINISTIC,
                score=1.0,
                passed=True,
            )
        )
        evaluation = EvaluationResult(id=new_id(), experiment=experiment, created_at=now)
        evaluation.metrics.append(
            MetricComparison(
                metric="success_rate", position=0, baseline_value=1.0, candidate_value=1.0
            )
        )
        session.add(project)
        session.commit()
        project_id = project.id

    with Session(engine) as session:
        loaded = session.get(Project, project_id)
        assert loaded is not None
        assert len(loaded.datasets) == 1
        assert len(loaded.system_versions) == 2
        assert len(loaded.experiments) == 1

        exp = loaded.experiments[0]
        assert exp.repeats == 2
        assert exp.baseline_version.version == "v1"
        assert exp.candidate_version.version == "v2"
        assert exp.release_policy is not None
        assert exp.release_policy.thresholds == {"latency_ms.p95": 0.2}
        assert exp.dataset.cases[0].input == "2+2?"
        assert exp.dataset.cases[0].origin is CaseOrigin.AUTHORED

        run = exp.evaluation_runs[0]
        assert (run.prompt_tokens, run.completion_tokens, run.latency_ms) == (3, 1, 12.5)
        assert run.case_result is not None
        assert run.case_result.scores[0].evaluator == "exact_match"
        assert run.case_result.scores[0].family is EvaluatorFamily.DETERMINISTIC

        assert exp.evaluation_results[0].metrics[0].metric == "success_rate"


# --- configuration & migration -------------------------------------------


def test_database_url_prefers_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url() == DEFAULT_DATABASE_URL
    assert "://" in DEFAULT_DATABASE_URL and "@" in DEFAULT_DATABASE_URL

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@db:5432/x")
    assert database_url() == "postgresql+psycopg://u@db:5432/x"


def test_initial_migration_builds_the_full_schema(tmp_path: Path) -> None:
    db_file = tmp_path / "migrated.sqlite"
    cfg = Config(str(Path("alembic.ini").resolve()))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    command.upgrade(cfg, "head")

    tables = set(inspect(create_engine(f"sqlite:///{db_file}")).get_table_names())
    assert tables >= _EXPECTED_TABLES
    assert "alembic_version" in tables


def test_foreign_key_helper_targets_are_valid() -> None:
    # every ForeignKey points at an existing column in the metadata
    for table in Base.metadata.tables.values():
        for column in table.c:
            for fk in column.foreign_keys:
                assert isinstance(fk, ForeignKey)
                assert fk.column is not None
