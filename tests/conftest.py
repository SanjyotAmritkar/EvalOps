"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from evalops.api.main import create_app
from evalops.db import Base, create_db_engine, session_factory


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A TestClient backed by a fresh temp-file SQLite database (no PostgreSQL)."""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.sqlite'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection: object, _: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    with TestClient(create_app(sessions=session_factory(engine))) as test_client:
        yield test_client
