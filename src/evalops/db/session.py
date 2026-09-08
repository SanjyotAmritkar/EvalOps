"""Session factory and unit-of-work lifecycle helper.

Repositories operate on a :class:`~sqlalchemy.orm.Session` supplied by the
caller; they never commit. Wrap a repository call sequence in
:func:`unit_of_work` to get commit-on-success / rollback-on-failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from evalops.db.engine import create_db_engine


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Return a configured :class:`~sqlalchemy.orm.sessionmaker`.

    ``expire_on_commit=False`` so domain objects mapped out of a committed
    session stay usable.
    """
    return sessionmaker(bind=engine or create_db_engine(), expire_on_commit=False)


@contextmanager
def unit_of_work(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session; commit on clean exit, roll back on any exception."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
