"""add async_job table

Durable lifecycle of a background experiment run (queued -> running ->
completed | failed), so PostgreSQL stays authoritative independent of
Celery/Redis.

Revision ID: dab5fa89c47d
Revises: 56a3222b520e
Create Date: 2026-09-08 20:58:41.250899

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dab5fa89c47d"
down_revision: Union[str, Sequence[str], None] = "56a3222b520e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "async_job",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="job_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("evaluation_result_id", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evaluation_result_id"],
            ["evaluation_result.id"],
            name=op.f("fk_async_job_evaluation_result_id_evaluation_result"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiment.id"],
            name=op.f("fk_async_job_experiment_id_experiment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_async_job")),
    )
    op.create_index(
        op.f("ix_async_job_experiment_id"), "async_job", ["experiment_id"], unique=False
    )
    op.create_index(
        op.f("ix_async_job_evaluation_result_id"),
        "async_job",
        ["evaluation_result_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_async_job_evaluation_result_id"), table_name="async_job")
    op.drop_index(op.f("ix_async_job_experiment_id"), table_name="async_job")
    op.drop_table("async_job")
