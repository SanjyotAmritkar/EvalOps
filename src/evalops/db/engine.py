"""Database URL resolution and engine construction.

Infrastructure only -- no ORM models, no sessions, no repositories.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine

#: Local development default. Overridden by the ``DATABASE_URL`` environment
#: variable. Contains no real credentials.
DEFAULT_DATABASE_URL = "postgresql+psycopg://evalops:evalops@localhost:5432/evalops"


def database_url() -> str:
    """Return the configured database URL (``DATABASE_URL`` env var, or the default)."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy :class:`Engine` for ``url`` (defaults to :func:`database_url`)."""
    return create_engine(url or database_url(), echo=echo)
