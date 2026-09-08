"""Request-scoped database session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from evalops.db import unit_of_work


def get_session(request: Request) -> Iterator[Session]:
    """Yield a session inside a unit of work: commit on success, roll back on error."""
    factory: sessionmaker[Session] = request.app.state.sessions
    with unit_of_work(factory) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
