"""Declarative base and shared column types for the persistence layer.

ORM models live here and in :mod:`evalops.db.models`; they are deliberately
separate from the frozen domain dataclasses in :mod:`evalops.domain`. This
module holds no business logic.
"""

from __future__ import annotations

from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# Stable, explicit constraint names so Alembic autogenerate diffs are readable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSONB on PostgreSQL (the production target); plain JSON elsewhere (e.g. the
# SQLite database used by the schema tests).
JSONMap = JSON().with_variant(JSONB(), "postgresql")

# Identifier columns mirror evalops.domain.ids.new_id(): 32-char uuid4 hex.
ID_LENGTH = 32


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
