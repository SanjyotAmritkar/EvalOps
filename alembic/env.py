"""Alembic environment for EvalOps.

The database URL comes from the ``sqlalchemy.url`` option when set explicitly
(used by the schema tests), otherwise from ``evalops.db.engine.database_url()``
(the ``DATABASE_URL`` environment variable, or the local default). No
credentials live in ``alembic.ini``.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from evalops.db import models as _models  # noqa: F401  -- register tables on Base.metadata
from evalops.db.base import Base
from evalops.db.engine import database_url

config = context.config

if config.config_file_name is not None:
    # ``disable_existing_loggers=False``: this configures Alembic's own logging
    # without silently disabling the application's loggers (``evalops.*``), which
    # matters when migrations run in-process (e.g. the schema tests) alongside
    # code that relies on ``evalops.obs`` structured logging.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _resolved_url() -> str:
    return config.get_main_option("sqlalchemy.url") or database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
