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
