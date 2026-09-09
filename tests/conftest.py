"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from evalops.api.main import create_app
from evalops.db import Base, create_db_engine, session_factory


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    """A sessionmaker over a fresh temp-file SQLite database (no PostgreSQL).

    Shared by the API ``client`` fixture and by tests that exercise the
    execution service directly, without HTTP.
    """
    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.sqlite'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection: object, _: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    return session_factory(engine)


@pytest.fixture
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    """A TestClient backed by the ``sessions`` fixture's database."""
    with TestClient(create_app(sessions=sessions)) as test_client:
        yield test_client


@pytest.fixture
def runnable_experiment(client: TestClient) -> str:
    """A persisted experiment whose two system versions answer one mock case.

    Setup goes through the API; the returned id is meant to be executed via the
    execution service or the Celery task (``backend: mock``, no network).
    """
    project_id = client.post("/projects", json={"name": "P"}).json()["id"]
    dataset_id = client.post(
        f"/projects/{project_id}/datasets",
        json={"name": "d", "version": 1, "cases": [{"input": "2+2?", "expected_output": "4"}]},
    ).json()["id"]

    def _version(version: str) -> str:
        return str(
            client.post(
                f"/projects/{project_id}/system-versions",
                json={
                    "name": "cfg",
                    "version": version,
                    "provider": "openai",
                    "model": "m",
                    "prompt_template": "Q: ${input}",
                    "parameters": {
                        "mock": {"responses": {"Q: 2+2?": "4"}, "default": "", "latency_ms": 40}
                    },
                },
            ).json()["id"]
        )

    return str(
        client.post(
            f"/projects/{project_id}/experiments",
            json={
                "dataset_id": dataset_id,
                "baseline_version_id": _version("v1"),
                "candidate_version_id": _version("v2"),
                "repeats": 2,
            },
        ).json()["id"]
    )
